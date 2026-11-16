"""
AeroSync Cryptographic Utilities

Provides AES-256-GCM encryption/decryption and hashing utilities.
Used by the workspace packager for session package encryption.

Usage:
    from shared.utils.crypto import generate_aes_key, aes_encrypt, aes_decrypt
    key = generate_aes_key()
    ciphertext = aes_encrypt(plaintext_bytes, key)
    plaintext = aes_decrypt(ciphertext, key)
"""

import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from shared.constants import AES_KEY_SIZE_BYTES, AES_NONCE_SIZE_BYTES


def generate_aes_key() -> bytes:
    """
    Generate a cryptographically secure random AES-256 key.
    
    Returns:
        bytes: 32-byte random key suitable for AES-256-GCM.
    """
    return os.urandom(AES_KEY_SIZE_BYTES)


def aes_encrypt(plaintext: bytes, key: bytes) -> bytes:
    """
    Encrypt data using AES-256-GCM (authenticated encryption).
    
    The output format is: nonce (12 bytes) || ciphertext || tag (16 bytes).
    The tag is appended automatically by AESGCM.
    
    Args:
        plaintext: The data to encrypt.
        key: 32-byte AES key.
        
    Returns:
        bytes: nonce + ciphertext + authentication tag.
        
    Raises:
        ValueError: If key is not 32 bytes.
    """
    if len(key) != AES_KEY_SIZE_BYTES:
        raise ValueError(f"AES key must be {AES_KEY_SIZE_BYTES} bytes, got {len(key)}")
    
    nonce = os.urandom(AES_NONCE_SIZE_BYTES)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    
    # Return nonce prepended to ciphertext (which includes the GCM tag)
    return nonce + ciphertext


def aes_decrypt(data: bytes, key: bytes) -> bytes:
    """
    Decrypt data encrypted with aes_encrypt.
    
    Expects input format: nonce (12 bytes) || ciphertext || tag (16 bytes).
    
    Args:
        data: The encrypted data (nonce + ciphertext + tag).
        key: 32-byte AES key (same key used for encryption).
        
    Returns:
        bytes: The decrypted plaintext.
        
    Raises:
        ValueError: If key is not 32 bytes or data is too short.
        cryptography.exceptions.InvalidTag: If authentication fails (data tampered).
    """
    if len(key) != AES_KEY_SIZE_BYTES:
        raise ValueError(f"AES key must be {AES_KEY_SIZE_BYTES} bytes, got {len(key)}")
    
    if len(data) < AES_NONCE_SIZE_BYTES + 16:  # nonce + minimum tag
        raise ValueError("Encrypted data is too short to contain nonce and tag")
    
    nonce = data[:AES_NONCE_SIZE_BYTES]
    ciphertext = data[AES_NONCE_SIZE_BYTES:]
    
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def sha256_hash(data: bytes) -> str:
    """
    Compute SHA-256 hash of data.
    
    Args:
        data: The data to hash.
        
    Returns:
        str: Hex-encoded SHA-256 hash.
    """
    return hashlib.sha256(data).hexdigest()


def sha256_hash_string(text: str) -> str:
    """
    Compute SHA-256 hash of a string.
    
    Args:
        text: The string to hash.
        
    Returns:
        str: Hex-encoded SHA-256 hash.
    """
    return sha256_hash(text.encode("utf-8"))
