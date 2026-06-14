import mimetypes
from typing import Optional
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.exceptions.http_exceptions import APIException


class S3Service:
    """S3 file service - provides file upload, download and management functionality"""

    def __init__(self):
        self.internal_endpoint_url = self._resolve_internal_endpoint(
            settings.AWS_ENDPOINT or None
        )
        self.s3_client = self._build_client(self.internal_endpoint_url)
        public_endpoint = settings.AWS_ENDPOINT_PUBLIC or settings.AWS_ENDPOINT
        self.public_endpoint_url = public_endpoint or None
        self.presign_client = self._build_client(self.public_endpoint_url)
        self.bucket_name = settings.AWS_BUCKET_NAME

    def generate_file_key(
        self,
        user_id: int,
        file_name: str,
        module: Optional[str] = None,
        sub_path: Optional[str] = None,
        module_id: Optional[int] = None,
    ) -> str:
        """
        Generate standardized S3 file key

        Args:
            user_id: User ID
            file_name: Original file name
            module: Module name (positions, interviews, etc.) - optional
            sub_path: Sub-path (jd, cv, cover_letter, etc.) - optional
            module_id: Module record ID (optional, e.g., position_id)

        Returns:
            Standardized file key path
        """
        # Get file extension
        file_ext = file_name.split(".")[-1].lower() if "." in file_name else ""

        # Generate unique filename
        unique_filename = f"{uuid4()}.{file_ext}" if file_ext else str(uuid4())

        # Build file path based on available parameters
        path_parts = [f"users/{user_id}"]

        if module:
            path_parts.append(module)
            if module_id:
                path_parts.append(str(module_id))

        if sub_path:
            path_parts.append(sub_path)

        path_parts.append(unique_filename)

        return "/".join(path_parts)

    def generate_presigned_upload_url(
        self,
        file_key: str,
        file_type: str,
        expires_in: int = 900,  # 15 minutes
        max_file_size: int = 10 * 1024 * 1024,  # 10MB
    ) -> dict:
        """
        Generate S3 presigned upload URL

        Args:
            file_key: S3 file key
            file_type: File MIME type
            expires_in: URL expiration time (seconds)
            max_file_size: Maximum file size (bytes)

        Returns:
            {
                "presigned_url": "...",
                "file_key": "...",
                "expires_in": 900
            }
        """
        try:
            # Generate presigned URL
            presigned_url = self.presign_client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": file_key,
                    "ContentType": file_type,
                },
                ExpiresIn=expires_in,
                HttpMethod="PUT",
            )

            return {
                "presigned_url": presigned_url,
                "file_key": file_key,
                "expires_in": expires_in,
                "max_file_size": max_file_size,
            }

        except (BotoCoreError, ClientError) as e:
            raise APIException(
                status_code=500, message=f"Failed to generate presigned URL: {str(e)}"
            )

    def generate_presigned_download_url(
        self, file_key: str, expires_in: int = 3600  # 1 hour
    ) -> str:
        """
        Generate S3 presigned download URL

        Args:
            file_key: S3 file key
            expires_in: URL expiration time (seconds)

        Returns:
            Presigned download URL
        """
        try:
            presigned_url = self.presign_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": file_key},
                ExpiresIn=expires_in,
            )
            return presigned_url

        except (BotoCoreError, ClientError) as e:
            raise APIException(
                status_code=500, message=f"Failed to generate download URL: {str(e)}"
            )

    def get_file_url(self, file_key: str) -> str:
        """
        Get file public access URL

        Args:
            file_key: S3 file key

        Returns:
            File S3 URL
        """
        public_endpoint = settings.AWS_ENDPOINT_PUBLIC or settings.AWS_ENDPOINT
        if public_endpoint:
            return f"{public_endpoint.rstrip('/')}/{self.bucket_name}/{file_key}"
        else:
            if settings.AWS_REGION and settings.AWS_REGION.startswith("cn-"):
                return f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com.cn/{file_key}"
            else:
                return f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{file_key}"

    def upload_bytes(
        self,
        file_key: str,
        data: bytes,
        content_type: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Upload bytes to S3 and return the file key.

        Args:
            file_key: S3 file key
            data: File bytes
            content_type: MIME type
            metadata: Optional S3 metadata

        Returns:
            Uploaded file key
        """
        try:
            params = {
                "Bucket": self.bucket_name,
                "Key": file_key,
                "Body": data,
                "ContentType": content_type,
            }
            if metadata:
                params["Metadata"] = {str(k): str(v) for k, v in metadata.items()}
            self.s3_client.put_object(**params)
            return file_key
        except (BotoCoreError, ClientError) as e:
            raise APIException(
                status_code=500, message=f"Failed to upload file: {str(e)}"
            )

    def download_bytes(self, file_key: str) -> bytes:
        """
        Download S3 object bytes.

        Args:
            file_key: S3 file key

        Returns:
            File bytes
        """
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=file_key)
            return response["Body"].read()
        except (BotoCoreError, ClientError) as e:
            raise APIException(
                status_code=500, message=f"Failed to download file: {str(e)}"
            )

    def _build_client(self, endpoint_url: str | None):
        return boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
            endpoint_url=endpoint_url,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def _resolve_internal_endpoint(self, endpoint_url: str | None) -> str | None:
        if not endpoint_url:
            return None

        parsed = urlparse(endpoint_url)
        hostname = parsed.hostname
        try:
            port = parsed.port
        except ValueError:
            port = None

        docker_minio_hosts = {"minio", f"{settings.PROJECT_NAME}-minio"}
        if hostname in docker_minio_hosts:
            if port != 9000:
                return urlunparse(
                    parsed._replace(
                        scheme=parsed.scheme or "http",
                        netloc=f"{hostname}:9000",
                    )
                )

        return endpoint_url

    def delete_file(self, file_key: str) -> bool:
        """
        Delete S3 file

        Args:
            file_key: S3 file key

        Returns:
            Whether deletion was successful
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_key)
            return True

        except (BotoCoreError, ClientError) as e:
            raise APIException(
                status_code=500, message=f"Failed to delete file: {str(e)}"
            )

    def validate_file_type(self, file_name: str, allowed_types: list) -> bool:
        """
        Validate file type

        Args:
            file_name: File name
            allowed_types: List of allowed file types (e.g., ['pdf', 'docx'])

        Returns:
            Whether file type is allowed
        """
        file_ext = file_name.split(".")[-1].lower() if "." in file_name else ""
        return file_ext in allowed_types

    def get_mime_type(self, file_name: str) -> str:
        """
        Get file MIME type

        Args:
            file_name: File name

        Returns:
            MIME type
        """
        mime_type, _ = mimetypes.guess_type(file_name)
        return mime_type or "application/octet-stream"


def get_s3_service() -> S3Service:
    """Get S3Service instance (dependency injection)"""
    return S3Service()
