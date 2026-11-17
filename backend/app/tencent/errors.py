from fastapi import HTTPException


class TencentError(HTTPException):
    def __init__(self, code, message, status=409):
        self.code = code
        super().__init__(status, {'code': code, 'message': message})
