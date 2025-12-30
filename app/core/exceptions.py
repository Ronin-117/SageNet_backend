from fastapi import HTTPException, status

class BaseAPIException(HTTPException):
    """Base class for all application errors"""
    pass

class AuthError(BaseAPIException):
    def __init__(self, detail: str = "Invalid or expired authentication credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"}
        )

class AccessDenied(BaseAPIException):
    def __init__(self, detail: str = "You do not have permission to access this resource"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

class DeviceNotFound(BaseAPIException):
    def __init__(self, device_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Device '{device_id}' not found or not registered."
        )

class MqttPublishError(BaseAPIException):
    def __init__(self, detail: str = "Failed to send command to the device network."):
        super().__init__(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)

class InfluxQueryError(BaseAPIException):
    def __init__(self, detail: str = "Database query failed."):
        super().__init__(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)