from pwdlib import PasswordHash


password_hasher = PasswordHash.recommended()

#Hash the password when registering
def hash_password(password: str) -> str:
    return password_hasher.hash(password)

#Verify the password when logging in - check whether PWD is matched with stoored hash
def verify_password(password: str, hashed_password: str) -> bool:
    return password_hasher.verify(password, hashed_password)