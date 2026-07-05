"""
MK Quantization Script — Convert fine-tuned model to GGUF

Converts the merged Hugging Face model to GGUF format and quantizes
to Q4_K_M for efficient inference on the i5-3470 via llama.cpp.

Quantization levels:
- Q8_0:   Highest quality, ~7GB for 3B model (tight fit on 8GB RAM)
- Q6_K:   Great quality, ~5.5GB (comfortable)
- Q5_K_M: Good quality, ~4.5GB (recommended balance)
- Q4_K_M: Good quality, ~3.5GB (best for i5-3470 with 8GB RAM)
- Q4_K_S: Slightly lower quality, ~3.2GB (most space efficient)
- Q3_K_M: Lower quality, ~2.8GB (if RAM is very tight)

For MK on i5-3470 (8GB RAM, ~5.5GB free after minimal OS):
  Q4_K_M is the sweet spot — quality stays high, fits easily.

Usage:
    python quantize.py --model_dir ./output/mk-qwen-3b-merged
    python quantize.py --model_dir ./output/mk-qwen-3b-merged --quant q5_k_m
    python quantize.py --model_dir ./output/mk-qwen-3b-merged --quant q4_k_m,q5_k_m

Requirements:
    - llama.cpp (cloned from GitHub)
    - Python 3.9+
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


# Default quantization types to produce
DEFAULT_QUANTS = ["q4_k_m", "q5_k_m"]

# llama.cpp repo
LLAMA_CPP_REPO = "https://github.com/ggerganov/llama.cpp.git"


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Quantize MK model to GGUF")
    parser.add_argument(
        "--model_dir", type=str, required=True,
        help="Path to the merged HF model directory"
    )
    parser.add_argument(
        "--output_dir", type=str, default="./output/mk-gguf",
        help="Output directory for GGUF files"
    )
    parser.add_argument(
        "--quant", type=str, default=",".join(DEFAULT_QUANTS),
        help="Quantization types (comma-separated). Options: q3_k_m, q4_k_s, q4_k_m, q5_k_m, q6_k, q8_0"
    )
    parser.add_argument(
        "--llama_cpp_dir", type=str, default="./llama.cpp",
        help="Path to llama.cpp directory (will clone if not exists)"
    )
    return parser.parse_args()



def ensure_llama_cpp(llama_cpp_dir: str) -> Path:
    """Ensure llama.cpp is available and built.

    Clones and builds llama.cpp if not present.

    Args:
        llama_cpp_dir: Path to llama.cpp directory

    Returns:
        Path to llama.cpp directory
    """
    llama_path = Path(llama_cpp_dir)

    if not llama_path.exists():
        print(f"[1/4] Cloning llama.cpp...")
        subprocess.run(
            ["git", "clone", "--depth", "1", LLAMA_CPP_REPO, str(llama_path)],
            check=True,
        )
    else:
        print(f"[1/4] llama.cpp found at {llama_path}")

    # Check if conversion script exists
    convert_script = llama_path / "convert_hf_to_gguf.py"
    if not convert_script.exists():
        # Try alternative location
        convert_script = llama_path / "convert-hf-to-gguf.py"

    if not convert_script.exists():
        print("  Installing llama.cpp Python dependencies...")
        req_file = llama_path / "requirements.txt"
        if req_file.exists():
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(req_file), "-q"],
                check=True,
            )
        # Also try requirements in convert directory
        convert_req = llama_path / "requirements" / "requirements-convert_hf_to_gguf.txt"
        if convert_req.exists():
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(convert_req), "-q"],
                check=True,
            )

    # Build quantize binary
    quantize_bin = llama_path / "build" / "bin" / "llama-quantize"
    if not quantize_bin.exists():
        quantize_bin = llama_path / "llama-quantize"

    if not quantize_bin.exists():
        print("  Building llama.cpp (for quantization binary)...")
        build_dir = llama_path / "build"
        build_dir.mkdir(exist_ok=True)
        subprocess.run(
            ["cmake", "..", "-DGGML_CUDA=OFF", "-DCMAKE_BUILD_TYPE=Release"],
            cwd=str(build_dir),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["cmake", "--build", ".", "--config", "Release", "-j", str(os.cpu_count())],
            cwd=str(build_dir),
            check=True,
            capture_output=True,
        )
        print("  llama.cpp built successfully")

    return llama_path


def convert_to_gguf(model_dir: str, llama_cpp_dir: Path, output_dir: str) -> Path:
    """Convert HuggingFace model to GGUF F16 format.

    Args:
        model_dir: Path to the merged HF model
        llama_cpp_dir: Path to llama.cpp
        output_dir: Output directory

    Returns:
        Path to the F16 GGUF file
    """
    print(f"[2/4] Converting model to GGUF (F16)...")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    f16_output = output_path / "mk-brain-f16.gguf"

    # Find conversion script
    convert_script = None
    for name in ["convert_hf_to_gguf.py", "convert-hf-to-gguf.py"]:
        candidate = llama_cpp_dir / name
        if candidate.exists():
            convert_script = candidate
            break

    if convert_script is None:
        raise FileNotFoundError(
            "Could not find convert_hf_to_gguf.py in llama.cpp directory"
        )

    cmd = [
        sys.executable, str(convert_script),
        model_dir,
        "--outfile", str(f16_output),
        "--outtype", "f16",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  STDERR: {result.stderr[-500:]}")
        raise RuntimeError(f"Conversion failed with code {result.returncode}")

    size_gb = f16_output.stat().st_size / (1024**3)
    print(f"  F16 GGUF created: {f16_output} ({size_gb:.2f} GB)")

    return f16_output



def quantize_model(f16_path: Path, llama_cpp_dir: Path, output_dir: str, quant_types: list) -> list:
    """Quantize the F16 GGUF to various quantization levels.

    Args:
        f16_path: Path to F16 GGUF file
        llama_cpp_dir: Path to llama.cpp
        output_dir: Output directory
        quant_types: List of quantization types to produce

    Returns:
        List of paths to quantized files
    """
    print(f"[3/4] Quantizing model...")

    output_path = Path(output_dir)
    quantized_files = []

    # Find quantize binary
    quantize_bin = None
    for candidate in [
        llama_cpp_dir / "build" / "bin" / "llama-quantize",
        llama_cpp_dir / "llama-quantize",
        llama_cpp_dir / "build" / "bin" / "quantize",
        llama_cpp_dir / "quantize",
    ]:
        if candidate.exists():
            quantize_bin = candidate
            break

    if quantize_bin is None:
        # Fall back to Python-based quantization via convert script
        print("  quantize binary not found, using Python-based approach...")
        for quant_type in quant_types:
            output_file = output_path / f"mk-brain-{quant_type}.gguf"
            # Use the convert script with outtype
            convert_script = None
            for name in ["convert_hf_to_gguf.py", "convert-hf-to-gguf.py"]:
                candidate = llama_cpp_dir / name
                if candidate.exists():
                    convert_script = candidate
                    break

            if convert_script:
                # Map quant type to outtype
                type_map = {
                    "q8_0": "q8_0",
                    "q4_k_m": "q4_0",  # Approximate
                    "q4_k_s": "q4_0",
                    "q5_k_m": "q5_0",
                    "q6_k": "q8_0",
                    "q3_k_m": "q4_0",
                }
                outtype = type_map.get(quant_type, "q4_0")

                cmd = [
                    sys.executable, str(convert_script),
                    str(f16_path.parent.parent / "mk-qwen-3b-merged"),
                    "--outfile", str(output_file),
                    "--outtype", outtype,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    size_gb = output_file.stat().st_size / (1024**3)
                    print(f"  {quant_type}: {output_file.name} ({size_gb:.2f} GB)")
                    quantized_files.append(output_file)
                else:
                    print(f"  {quant_type}: FAILED - {result.stderr[-200:]}")
        return quantized_files

    # Use the native quantize binary
    for quant_type in quant_types:
        output_file = output_path / f"mk-brain-{quant_type}.gguf"

        cmd = [
            str(quantize_bin),
            str(f16_path),
            str(output_file),
            quant_type.upper(),
        ]

        print(f"  Quantizing to {quant_type}...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0 and output_file.exists():
            size_gb = output_file.stat().st_size / (1024**3)
            print(f"    -> {output_file.name} ({size_gb:.2f} GB)")
            quantized_files.append(output_file)
        else:
            print(f"    -> FAILED: {result.stderr[-200:]}")

    return quantized_files


def create_model_card(output_dir: str, quant_files: list, model_dir: str):
    """Create a model card/info file with the quantized model.

    Args:
        output_dir: Output directory
        quant_files: List of quantized file paths
        model_dir: Original model directory
    """
    print(f"[4/4] Creating model card...")

    output_path = Path(output_dir)
    card_path = output_path / "README.md"

    content = """# MK Brain — Quantized GGUF Model

Custom fine-tuned Qwen2.5-3B-Instruct for MK AI Operating System.

## Purpose
MK's local decision-making brain. Handles:
- Intent parsing and tool selection
- Routing decisions (local vs cloud)
- Multi-step task planning
- Safety checks on dangerous operations
- Homelab management reasoning

## Files
"""

    for qf in quant_files:
        size_gb = qf.stat().st_size / (1024**3)
        content += f"- `{qf.name}` — {size_gb:.2f} GB\n"

    content += """
## Recommended
- **For i5-3470 (8GB RAM):** Use `mk-brain-q4_k_m.gguf` (~3.5GB)
- **If RAM allows:** Use `mk-brain-q5_k_m.gguf` (~4.5GB) for better quality

## Usage with llama.cpp

```bash
# Start server
./llama-server -m mk-brain-q4_k_m.gguf -c 2048 -ngl 0 --host 0.0.0.0 --port 8080

# Or use the MK deployment scripts:
cd deploy/
./start-llm-server.sh
```

## Base Model
- Qwen/Qwen2.5-3B-Instruct
- Fine-tuned with QLoRA (rank 64, alpha 128)
- Training data: MK-specific agent reasoning examples

## Hardware Requirements
- Minimum: 4GB RAM free (Q4_K_M)
- Recommended: 6GB RAM free (Q5_K_M)
- CPU: Any x86_64 with AVX2 (i5-3470 works)
"""

    card_path.write_text(content)
    print(f"  Model card written to {card_path}")



def main():
    """Main quantization pipeline."""
    args = parse_args()

    print("=" * 60)
    print("  MK Quantization — GGUF Conversion")
    print("=" * 60)
    print(f"  Model:   {args.model_dir}")
    print(f"  Output:  {args.output_dir}")
    print(f"  Quants:  {args.quant}")
    print("=" * 60)
    print("")

    # Validate model directory
    model_path = Path(args.model_dir)
    if not model_path.exists():
        print(f"[ERROR] Model directory not found: {args.model_dir}")
        print("  Run finetune.py first to create the merged model.")
        sys.exit(1)

    quant_types = [q.strip() for q in args.quant.split(",")]

    # Step 1: Ensure llama.cpp is available
    llama_cpp_dir = ensure_llama_cpp(args.llama_cpp_dir)

    # Step 2: Convert to F16 GGUF
    f16_path = convert_to_gguf(args.model_dir, llama_cpp_dir, args.output_dir)

    # Step 3: Quantize
    quant_files = quantize_model(f16_path, llama_cpp_dir, args.output_dir, quant_types)

    # Step 4: Create model card
    if quant_files:
        create_model_card(args.output_dir, quant_files, args.model_dir)

    # Clean up F16 (it's large and not needed for deployment)
    if f16_path.exists() and quant_files:
        print(f"\nRemoving F16 file (no longer needed)...")
        f16_path.unlink()
        print(f"  Removed {f16_path.name}")

    print("")
    print("=" * 60)
    print("  Quantization complete!")
    print("=" * 60)
    print("")
    if quant_files:
        print("  Files ready for deployment:")
        for qf in quant_files:
            size_gb = qf.stat().st_size / (1024**3)
            print(f"    {qf.name} ({size_gb:.2f} GB)")
        print("")
        print(f"  Copy to your i5-3470:")
        print(f"    scp {args.output_dir}/mk-brain-q4_k_m.gguf user@mk-brain:/opt/mk/models/")
        print("")
        print("  Then use training/deploy/ scripts to run it.")
    else:
        print("  [WARN] No quantized files produced. Check errors above.")


if __name__ == "__main__":
    main()
