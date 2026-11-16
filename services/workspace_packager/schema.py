"""
AeroSync Workspace Packager Schema

Metadata structures for the encrypted workspace package.
"""

from dataclasses import dataclass, field


@dataclass
class PackageHeader:
    """Header information embedded at the start of a package."""
    version: str = "1.0"
    checksum_sha256: str = ""
    timestamp_iso: str = ""
    source_device_id: str = ""


@dataclass
class TransferPackage:
    """A fully prepared workspace package ready for upload."""
    header: PackageHeader = field(default_factory=PackageHeader)
    encrypted_payload: bytes = b""
    aes_key: bytes = b""
    
    @property
    def total_size_bytes(self) -> int:
        """Get the total size of the encrypted payload."""
        return len(self.encrypted_payload)
