"""
MK Fine-Tuning Script — QLoRA on Qwen2.5-3B-Instruct

Fine-tunes Qwen2.5-3B-Instruct using QLoRA (4-bit quantized LoRA)
to become MK's local decision-making brain.

Requirements (installed via aws/setup.sh):
- torch
- transformers
- peft
- bitsandbytes
- datasets
- trl
- accelerate

Usage:
    python finetune.py --data_dir ../data --output_dir ./mk-model

Expected hardware: 1x A10G (24GB VRAM) or T4 (16GB VRAM)
Expected time: 1-3 hours depending on GPU
Expected cost: $3-10 on AWS
"""

import argparse
import json
import os
from pathlib import Path

import torch
from datasets import Dataset, load_dataset
from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from trl import SFTTrainer, SFTConfig



# ============================================================
# Configuration
# ============================================================

# Base model from Hugging Face
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"

# QLoRA configuration
LORA_R = 64              # LoRA rank (higher = more capacity, more VRAM)
LORA_ALPHA = 128         # LoRA alpha (scaling factor, usually 2x rank)
LORA_DROPOUT = 0.05      # Dropout for regularization
LORA_TARGET_MODULES = [  # Which layers to fine-tune
    "q_proj", "k_proj", "v_proj", "o_proj",  # Attention
    "gate_proj", "up_proj", "down_proj",       # MLP
]

# Training hyperparameters
EPOCHS = 3               # Number of training epochs
BATCH_SIZE = 4           # Per-device batch size
GRAD_ACCUM = 4           # Gradient accumulation steps (effective batch = 16)
LEARNING_RATE = 2e-4     # Learning rate (standard for QLoRA)
MAX_SEQ_LENGTH = 2048    # Max sequence length
WARMUP_RATIO = 0.05      # Warmup proportion
WEIGHT_DECAY = 0.01      # Weight decay for regularization
LR_SCHEDULER = "cosine"  # Learning rate scheduler


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Fine-tune Qwen2.5-3B for MK")
    parser.add_argument(
        "--data_dir", type=str, default="../data",
        help="Directory containing mk_train.jsonl and mk_val.jsonl"
    )
    parser.add_argument(
        "--output_dir", type=str, default="./mk-qwen-3b",
        help="Output directory for the fine-tuned model"
    )
    parser.add_argument(
        "--base_model", type=str, default=BASE_MODEL,
        help="Base model to fine-tune"
    )
    parser.add_argument(
        "--epochs", type=int, default=EPOCHS,
        help="Number of training epochs"
    )
    parser.add_argument(
        "--batch_size", type=int, default=BATCH_SIZE,
        help="Per-device batch size"
    )
    parser.add_argument(
        "--lr", type=float, default=LEARNING_RATE,
        help="Learning rate"
    )
    parser.add_argument(
        "--max_seq_length", type=int, default=MAX_SEQ_LENGTH,
        help="Maximum sequence length"
    )
    parser.add_argument(
        "--lora_r", type=int, default=LORA_R,
        help="LoRA rank"
    )
    parser.add_argument(
        "--resume", type=str, default=None,
        help="Path to checkpoint to resume from"
    )
    return parser.parse_args()



def load_training_data(data_dir: str) -> tuple:
    """Load training and validation datasets from JSONL files.

    Args:
        data_dir: Path to directory containing mk_train.jsonl and mk_val.jsonl

    Returns:
        Tuple of (train_dataset, val_dataset)
    """
    data_path = Path(data_dir)
    train_path = data_path / "mk_train.jsonl"
    val_path = data_path / "mk_val.jsonl"

    if not train_path.exists():
        raise FileNotFoundError(f"Training data not found: {train_path}")
    if not val_path.exists():
        raise FileNotFoundError(f"Validation data not found: {val_path}")

    train_dataset = load_dataset("json", data_files=str(train_path), split="train")
    val_dataset = load_dataset("json", data_files=str(val_path), split="train")

    print(f"Loaded {len(train_dataset)} training examples")
    print(f"Loaded {len(val_dataset)} validation examples")

    return train_dataset, val_dataset


def create_quantization_config() -> BitsAndBytesConfig:
    """Create 4-bit quantization config for QLoRA.

    Returns:
        BitsAndBytesConfig for 4-bit quantization with NF4.
    """
    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,  # Nested quantization for more savings
    )


def create_lora_config(lora_r: int) -> LoraConfig:
    """Create LoRA configuration.

    Args:
        lora_r: LoRA rank

    Returns:
        LoraConfig for PEFT
    """
    return LoraConfig(
        r=lora_r,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=LORA_TARGET_MODULES,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )



def load_model_and_tokenizer(model_name: str, bnb_config: BitsAndBytesConfig):
    """Load the base model and tokenizer.

    Args:
        model_name: Hugging Face model name
        bnb_config: Quantization configuration

    Returns:
        Tuple of (model, tokenizer)
    """
    print(f"Loading model: {model_name}")

    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=True,
        padding_side="right",
    )

    # Ensure pad token exists
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )

    # Prepare model for QLoRA training
    model = prepare_model_for_kbit_training(model)
    model.config.use_cache = False  # Disable for training

    print(f"Model loaded. Parameters: {model.num_parameters():,}")

    return model, tokenizer


def formatting_func(example):
    """Format dataset example into the chat template string.

    Converts the messages list into the model's chat format.

    Args:
        example: Dataset example with 'messages' field

    Returns:
        Formatted text string
    """
    messages = example["messages"]
    # Use Qwen's chat template format
    text = ""
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "system":
            text += f"<|im_start|>system\n{content}<|im_end|>\n"
        elif role == "user":
            text += f"<|im_start|>user\n{content}<|im_end|>\n"
        elif role == "assistant":
            text += f"<|im_start|>assistant\n{content}<|im_end|>\n"
    return text



def main():
    """Main training function."""
    args = parse_args()

    print("=" * 60)
    print("  MK Fine-Tuning — QLoRA on Qwen2.5-3B-Instruct")
    print("=" * 60)
    print(f"  Base model:     {args.base_model}")
    print(f"  Data directory: {args.data_dir}")
    print(f"  Output:         {args.output_dir}")
    print(f"  Epochs:         {args.epochs}")
    print(f"  Batch size:     {args.batch_size} (effective: {args.batch_size * GRAD_ACCUM})")
    print(f"  Learning rate:  {args.lr}")
    print(f"  LoRA rank:      {args.lora_r}")
    print(f"  Max seq length: {args.max_seq_length}")
    print(f"  Device:         {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")
    print(f"  VRAM:           {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f}GB" if torch.cuda.is_available() else "")
    print("=" * 60)

    # Load data
    train_dataset, val_dataset = load_training_data(args.data_dir)

    # Setup quantization and LoRA
    bnb_config = create_quantization_config()
    lora_config = create_lora_config(args.lora_r)

    # Load model
    model, tokenizer = load_model_and_tokenizer(args.base_model, bnb_config)

    # Apply LoRA
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Training arguments
    training_args = SFTConfig(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=GRAD_ACCUM,
        learning_rate=args.lr,
        weight_decay=WEIGHT_DECAY,
        lr_scheduler_type=LR_SCHEDULER,
        warmup_ratio=WARMUP_RATIO,
        max_seq_length=args.max_seq_length,
        # Optimization
        bf16=True,
        gradient_checkpointing=True,
        optim="paged_adamw_8bit",
        # Logging
        logging_steps=10,
        logging_first_step=True,
        # Evaluation
        eval_strategy="steps",
        eval_steps=50,
        # Saving
        save_strategy="steps",
        save_steps=100,
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        # Misc
        report_to="none",
        seed=42,
        dataset_text_field="text",
    )

    # Create trainer
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        processing_class=tokenizer,
        formatting_func=formatting_func,
    )

    # Train
    print("\nStarting training...")
    if args.resume:
        trainer.train(resume_from_checkpoint=args.resume)
    else:
        trainer.train()

    # Save final model
    print(f"\nSaving model to {args.output_dir}")
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    # Save merged model (LoRA weights merged into base)
    merged_dir = f"{args.output_dir}-merged"
    print(f"Merging LoRA weights and saving to {merged_dir}")

    # Reload in full precision for merging
    from peft import PeftModel

    base_model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )
    merged_model = PeftModel.from_pretrained(base_model, args.output_dir)
    merged_model = merged_model.merge_and_unload()
    merged_model.save_pretrained(merged_dir)
    tokenizer.save_pretrained(merged_dir)

    print("\n" + "=" * 60)
    print("  Training complete!")
    print(f"  LoRA adapter: {args.output_dir}")
    print(f"  Merged model: {merged_dir}")
    print("=" * 60)
    print("\nNext step: quantize the merged model to GGUF")
    print(f"  python quantize.py --model_dir {merged_dir}")


if __name__ == "__main__":
    main()
