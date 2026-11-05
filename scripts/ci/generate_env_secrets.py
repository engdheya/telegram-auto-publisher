import secrets, pathlib, sys
from cryptography.fernet import Fernet
p = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.env'); s = p.read_text()
s = s.replace('CHANGE_ME_GENERATE_FERNET_32_BYTE_BASE64_KEY', Fernet.generate_key().decode())
s = s.replace('CHANGE_ME_GENERATE_WITH_SECRETS_TOKEN_URLSAFE_48', secrets.token_urlsafe(48))
s = s.replace('CHANGE_ME_STRONG_ADMIN_PASSWORD_123!', 'Closure-' + secrets.token_urlsafe(9))
p.write_text(s)
print('rotated: SESSION_ENCRYPTION_KEY, JWT_SECRET_KEY, INITIAL_ADMIN_PASSWORD')
