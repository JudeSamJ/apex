import os
import re
import sys

# High-entropy secret signatures
SECRET_PATTERNS = [
    (re.compile(r"sk_live_[0-9a-zA-Z]{24}"), "Stripe Live Secret Key"),
    (re.compile(r"sk_test_[0-9a-zA-Z]{24}"), "Stripe Test Secret Key"),
    (re.compile(r"-----BEGIN [A-Z]+ PRIVATE KEY-----"), "PEM Private Key Block"),
    (re.compile(r"aws_secret_access_key\s*=\s*['\"][0-9a-zA-Z/+]{40}['\"]", re.IGNORECASE), "AWS Secret Access Key"),
]

def scan_files():
    print("=== RUNNING SECRETS & CREDENTIALS AUDIT ===")
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    
    violations = []
    
    # Files/directories to exclude
    exclude_dirs = {".git", "venv", "node_modules", "dist", ".agents"}
    exclude_files = {"pre_commit_secrets_check.py"}

    for root, dirs, files in os.walk(root_dir):
        # Exclude directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for f in files:
            if f in exclude_files:
                continue
            # Scan text files only
            if f.endswith((".py", ".ts", ".tsx", ".env", ".json", ".md")):
                path = os.path.join(root, f)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as file:
                        content = file.read()
                    
                    for pattern, name in SECRET_PATTERNS:
                        if pattern.search(content):
                            violations.append(f"Hardcoded {name} detected in: {os.path.relpath(path, root_dir)}")
                except Exception as e:
                    print(f"Skipping audit for {f} due to read error: {e}")

    if violations:
        print("\n[!] Credentials Violation: Hardcoded secrets found committed in code:")
        for v in violations:
            print(f" - {v}")
        return 1
    else:
        print("\n[+] Secrets check passed: No high-entropy secrets or private keys detected in workspace.")
        return 0

if __name__ == "__main__":
    sys.exit(scan_files())
