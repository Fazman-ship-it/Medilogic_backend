import secrets

def generate_invite_code(prefix="ORG"):
    return f"{prefix}-{secrets.token_hex(4).upper()}"