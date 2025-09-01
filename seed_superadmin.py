from app.auth import get_password_hash  # adjust path if needed

password = "Ademola@15"  # your super admin password
hashed = get_password_hash(password)

print("Hashed password:", hashed)