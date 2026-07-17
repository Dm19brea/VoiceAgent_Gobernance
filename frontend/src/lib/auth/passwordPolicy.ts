/**
 * Advisory mirror of `backend/src/domain/password_policy.py`.
 *
 * This is UX-only live feedback for the `/setup` form. `POST /auth/setup` is
 * the authoritative validator; drift between the two is safe because the
 * server always re-validates and never trusts this client-side check.
 */

export const MIN_LENGTH = 12;

export type PasswordRule = "min_length" | "uppercase" | "lowercase" | "digit" | "special";

const UPPERCASE_RE = /[A-Z]/;
const LOWERCASE_RE = /[a-z]/;
const DIGIT_RE = /\d/;
const SPECIAL_RE = /[^A-Za-z0-9]/;

/** Returns every unmet policy rule; an empty array means the password is compliant. */
export function validatePassword(password: string): PasswordRule[] {
  const violations: PasswordRule[] = [];
  if (password.length < MIN_LENGTH) violations.push("min_length");
  if (!UPPERCASE_RE.test(password)) violations.push("uppercase");
  if (!LOWERCASE_RE.test(password)) violations.push("lowercase");
  if (!DIGIT_RE.test(password)) violations.push("digit");
  if (!SPECIAL_RE.test(password)) violations.push("special");
  return violations;
}
