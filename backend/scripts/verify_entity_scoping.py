import sys
import os
import re

def verify_entity_scoping():
    print("=== RUNNING ENTITY SCOPING & DATA ISOLATION AUDIT ===")
    
    # 1. Gather all models and verify entity_id
    models_dir = os.path.join(os.path.dirname(__file__), "..", "app")
    models_pattern = re.compile(r"class\s+(\w+)\(Base\):")
    entity_id_pattern = re.compile(r"entity_id\s*=")

    violations = []
    
    for root, dirs, files in os.walk(models_dir):
        for f in files:
            if f == "models.py":
                path = os.path.join(root, f)
                with open(path, "r", encoding="utf-8") as file_content:
                    content = file_content.read()
                    
                matches = models_pattern.findall(content)
                for model in matches:
                    # Allow Role or other cross-entity system configurations to skip entity_id scoping
                    if model in ["Role", "LedgerEntry"]:
                        continue
                    
                    # Verify model code block has entity_id defined
                    # Get class definition start index
                    class_idx = content.find(f"class {model}(Base):")
                    # Search within this class block (until the next class or end of file)
                    next_class = re.search(r"class\s+\w+\(Base\):", content[class_idx + 1:])
                    class_block = content[class_idx : class_idx + next_class.start() + 1] if next_class else content[class_idx:]
                    
                    if not entity_id_pattern.search(class_block):
                        violations.append(f"Model '{model}' in {os.path.basename(root)}/models.py lacks 'entity_id' column")

    # 2. Check for Direct Ledger modifications outside app/ledger/
    ledger_write_pattern = re.compile(r"(LedgerEntry|db\.add\(LedgerEntry|db\.query\(LedgerEntry)")
    for root, dirs, files in os.walk(models_dir):
        # Exclude tests, app/ledger and app/database.py
        if "ledger" in root or "tests" in root:
            continue
        for f in files:
            if f == "database.py":
                continue
            if f.endswith(".py"):
                path = os.path.join(root, f)
                with open(path, "r", encoding="utf-8") as file_content:
                    content = file_content.read()
                
                if ledger_write_pattern.search(content):
                    violations.append(f"Direct access to LedgerEntry detected in file: {path}")

    # Output results
    if violations:
        print("\n[!] Consistency Violations Found:")
        for v in violations:
            print(f" - {v}")
        return 1
    else:
        print("\n[+] Consistency Check passed: All models properly scoped, and Ledger access is securely isolated.")
        return 0

if __name__ == "__main__":
    sys.exit(verify_entity_scoping())
