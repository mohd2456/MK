/**
 * LoginPage Component
 * ====================
 * PIN-based authentication screen.
 * Dark, centered, minimal - just the MK logo and a PIN pad.
 *
 * Features:
 * - 4-8 digit PIN entry via number pad
 * - Animated dot indicators for entered digits
 * - Lockout after too many failed attempts
 * - Subtle accent glow on the logo
 * - Auto-submit when PIN reaches configured length
 */

import { useState, useCallback, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Delete, Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/authStore";
import { post } from "@/lib/api";
import type { AuthResponse } from "@/types/api";

const PIN_LENGTH = 4; // Default PIN length (can be 4-8)

export function LoginPage() {
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [shake, setShake] = useState(false);
  const navigate = useNavigate();
  const { login, recordFailedAttempt, isLockedOut, getRemainingLockoutSeconds } =
    useAuthStore();

  const [lockoutSeconds, setLockoutSeconds] = useState(0);

  // Update lockout countdown
  useEffect(() => {
    if (!isLockedOut()) return;
    const interval = setInterval(() => {
      const remaining = getRemainingLockoutSeconds();
      setLockoutSeconds(remaining);
      if (remaining <= 0) setLockoutSeconds(0);
    }, 1000);
    return () => clearInterval(interval);
  }, [isLockedOut, getRemainingLockoutSeconds]);

  const handleSubmit = useCallback(
    async (enteredPin: string) => {
      if (isLockedOut()) {
        setError(`Too many attempts. Try again in ${getRemainingLockoutSeconds()}s`);
        return;
      }

      setIsSubmitting(true);
      setError("");

      try {
        const response = await post<AuthResponse>("/auth/login", {
          pin: enteredPin,
        });
        login(response.token, response.expires);
        navigate("/", { replace: true });
      } catch {
        recordFailedAttempt();
        setError("Incorrect PIN");
        setPin("");
        setShake(true);
        setTimeout(() => setShake(false), 500);
      } finally {
        setIsSubmitting(false);
      }
    },
    [isLockedOut, getRemainingLockoutSeconds, login, navigate, recordFailedAttempt]
  );

  const handleDigit = useCallback(
    (digit: string) => {
      if (isSubmitting || isLockedOut()) return;
      const newPin = pin + digit;
      setPin(newPin);
      setError("");

      // Auto-submit when PIN length reached
      if (newPin.length >= PIN_LENGTH) {
        handleSubmit(newPin);
      }
    },
    [pin, isSubmitting, isLockedOut, handleSubmit]
  );

  const handleBackspace = useCallback(() => {
    setPin((p) => p.slice(0, -1));
    setError("");
  }, []);

  // Keyboard support
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key >= "0" && e.key <= "9") {
        handleDigit(e.key);
      } else if (e.key === "Backspace") {
        handleBackspace();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleDigit, handleBackspace]);

  const locked = isLockedOut();

  return (
    <div className="h-full w-full flex flex-col items-center justify-center bg-mk-base p-4">
      {/* Background subtle gradient */}
      <div className="fixed inset-0 bg-[radial-gradient(ellipse_at_center,_rgba(0,212,255,0.03)_0%,_transparent_70%)] pointer-events-none" />

      <div className="relative flex flex-col items-center gap-8 w-full max-w-xs">
        {/* Logo */}
        <div className="flex flex-col items-center gap-3">
          <div
            className={cn(
              "w-16 h-16 rounded-[16px] flex items-center justify-center",
              "bg-mk-accent/10 border border-mk-accent/30",
              "shadow-[0_0_40px_rgba(0,212,255,0.15)]",
              "transition-all duration-500"
            )}
          >
            <span className="text-mk-accent font-bold text-2xl">MK</span>
          </div>
          <div className="text-center">
            <h1 className="text-xl font-semibold text-mk-text-primary">MK OS</h1>
            <p className="text-sm text-mk-text-muted mt-0.5">Enter your PIN</p>
          </div>
        </div>

        {/* PIN dots */}
        <div
          className={cn(
            "flex items-center gap-3",
            shake && "animate-[shake_0.4s_ease-in-out]"
          )}
        >
          {Array.from({ length: PIN_LENGTH }).map((_, i) => (
            <div
              key={i}
              className={cn(
                "w-3.5 h-3.5 rounded-full transition-all duration-200",
                i < pin.length
                  ? "bg-mk-accent scale-110 shadow-[0_0_8px_rgba(0,212,255,0.4)]"
                  : "bg-mk-border"
              )}
            />
          ))}
        </div>

        {/* Error message */}
        <div className="h-5 flex items-center">
          {error && (
            <p className="text-xs text-mk-error flex items-center gap-1 animate-fade-in">
              <Lock size={12} />
              {error}
            </p>
          )}
          {locked && (
            <p className="text-xs text-mk-warning animate-fade-in">
              Locked for {lockoutSeconds}s
            </p>
          )}
        </div>

        {/* Number pad */}
        <div className="grid grid-cols-3 gap-3 w-full max-w-[280px] mx-auto">
          {["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "back"].map(
            (key) => {
              if (key === "") return <div key="empty" />;
              if (key === "back") {
                return (
                  <button
                    key="back"
                    onClick={handleBackspace}
                    disabled={pin.length === 0 || isSubmitting}
                    className={cn(
                      "h-14 rounded-[12px] flex items-center justify-center",
                      "text-mk-text-muted hover:text-mk-text-primary",
                      "hover:bg-mk-elevated active:bg-mk-overlay",
                      "transition-all duration-[150ms]",
                      "disabled:opacity-30 disabled:pointer-events-none"
                    )}
                    aria-label="Backspace"
                  >
                    <Delete size={20} />
                  </button>
                );
              }
              return (
                <button
                  key={key}
                  onClick={() => handleDigit(key)}
                  disabled={locked || isSubmitting || pin.length >= PIN_LENGTH}
                  className={cn(
                    "h-14 sm:h-14 min-h-[56px] rounded-[12px] flex items-center justify-center",
                    "text-lg font-medium text-mk-text-primary",
                    "bg-mk-surface border border-mk-border",
                    "hover:bg-mk-elevated hover:border-mk-border-strong",
                    "active:scale-[0.95] active:bg-mk-overlay",
                    "transition-all duration-[150ms]",
                    "disabled:opacity-30 disabled:pointer-events-none",
                    "touch-manipulation"
                  )}
                >
                  {key}
                </button>
              );
            }
          )}
        </div>

        {/* Footer note */}
        <p className="text-[11px] text-mk-text-muted text-center mt-4">
          Forgot PIN? Reset via CLI on the server.
        </p>
      </div>

      {/* Shake animation keyframes */}
      <style>{`
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          20% { transform: translateX(-8px); }
          40% { transform: translateX(8px); }
          60% { transform: translateX(-4px); }
          80% { transform: translateX(4px); }
        }
      `}</style>
    </div>
  );
}
