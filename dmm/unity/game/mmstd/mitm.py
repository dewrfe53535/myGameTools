import urllib.parse
import base64
import os
import urllib
import json
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad, pad
from Crypto.Hash import SHA1
from mitmproxy import http, ctx
from mitmcommon import *


setattr(http.Request, 'noQueryPath', setmitmNoQueryPath())


class RsaInterceptor:
    def __init__(self):
        self.private_key = rsa.generate_private_key(65537, 1024, default_backend())
        self.public_key = self.private_key.public_key()
        self.original_pub_numbers = None
        self.secret = ''

    def request(self, flow: http.HTTPFlow) -> None:
        if flow.request.headers.get('X-Ag-Protocol') == '3':
            ctx.log.info("Intercepting RSA request")
            payload = urllib.parse.unquote(flow.request.content.decode())
            flow.request.content = self.modify_request(payload)

    def generate_nonce(self):
        return base64.b64encode(os.urandom(16)).decode()

    def sign(self, original_data, nonce: str):
        signature_source = f"{self.secret}@{original_data}@{nonce}".encode()
        return self.private_key.sign(signature_source, padding.PKCS1v15(), hashes.SHA256())

    def modify_request(self, original_payload):
        parts = urllib.parse.unquote(original_payload).split('\n')

        # 保存原始公钥信息
        self.original_pub_numbers = self.parse_v16(base64.b64decode(parts[2]))

        # 生成新签名数据
        nonce = self.generate_nonce()
        signature = self.sign(urllib.parse.unquote(parts[0]), nonce)
        v13_data = (len(nonce).to_bytes(2, 'big') + len(signature).to_bytes(2, 'big')
                    + nonce.encode() + signature)
        base64_v13 = base64.b64encode(v13_data).decode()

        # 生成新公钥数据
        pub = self.public_key.public_numbers()
        modulus = pub.n.to_bytes(128, 'big')
        exponent = pub.e.to_bytes(3, 'big')
        v16_data = (len(modulus).to_bytes(2, 'big') + len(exponent).to_bytes(2, 'big')
                    + modulus + exponent)
        base64_v16 = base64.b64encode(v16_data).decode()

        return urllib.parse.quote(f"{parts[0]}\n{base64_v13}\n{base64_v16}", safe='').encode()

    def parse_v16(self, data):
        mod_len = int.from_bytes(data[:2], 'big')
        exp_len = int.from_bytes(data[2:4], 'big')
        return RSAPublicNumbers(
            e=int.from_bytes(data[4 + mod_len:4 + mod_len + exp_len], 'big'),
            n=int.from_bytes(data[4:4 + mod_len], 'big')
        )

    def response(self, flow: http.HTTPFlow) -> None:
        if flow.request.headers.get('X-Ag-Protocol') == '3':
            ctx.log.info("Intercepting RSA response")
            decrypted = self.decrypt_response(flow.response.text)
            flow.metadata['decrypted_response'] = decrypted
            flow.comment += decrypted
            flow.response.content = self.re_encrypt_data(decrypted)
            if caeskey := json.loads(decrypted)['data'].get('kdfp'):
                apiAesInstance.set_key(caeskey)

    def decrypt_response(self, encrypted_data):
        return ''.join(
            self.private_key.decrypt(
                base64.b64decode(chunk.strip()),
                padding.OAEP(
                    mgf=padding.MGF1(hashes.SHA1()),
                    algorithm=hashes.SHA1(),
                    label=None
                )
            ).decode() for chunk in encrypted_data.split('\n')[:-1]
        )

    def re_encrypt_data(self, data):
        public_key = self.original_pub_numbers.public_key(default_backend())
        return b'\n'.join(
            base64.b64encode(public_key.encrypt(
                data[i:i + 62].encode(),
                padding.OAEP(
                    mgf=padding.MGF1(hashes.SHA1()),
                    algorithm=hashes.SHA1(),
                    label=None
                )
            )) for i in range(0, len(data), 62)
        ) + b'\n'


class AesInterceptor:
    def __init__(self):
        self.aes_key = None

    def set_key(self, raw_key_str: str):
        """设置AES密钥（由其他addon调用）"""
        try:
            self.aes_key = raw_key_str.encode('utf-8')
            ctx.log.info(f"AES key set successfully: {raw_key_str}")
        except Exception as e:
            ctx.log.error(f"Key setting failed: {str(e)}")

    def _decrypt_data(self, ciphertext: bytes) -> str:
        """执行实际的AES解密"""
        if not self.aes_key:
            ctx.log.error("No AES key configured!")
            return ""

        try:
            # 分割盐(32)、IV(16)和实际密文
            salt = ciphertext[:32]
            iv = ciphertext[32:48]
            encrypted = ciphertext[48:]

            # 生成密钥
            key = PBKDF2(
                password=self.aes_key,
                salt=salt,
                dkLen=32,
                count=10000,
                hmac_hash_module=SHA1
            )

            # 解密数据
            cipher = AES.new(key, AES.MODE_CBC, iv)
            decrypted = unpad(cipher.decrypt(encrypted), AES.block_size)
            return decrypted.decode('utf-8', errors='replace')

        except Exception as e:
            ctx.log.error(f"Decryption failed: {str(e)}")
            return "[DECRYPTION ERROR]"

    def _process_flow(self, flow: http.HTTPFlow, is_request: bool):
        """通用处理逻辑"""
        headers = flow.request.headers if is_request else flow.response.headers
        content = flow.request.content if is_request else flow.response.content

        if headers.get('X-Ag-Protocol', '') == '2' and content:
            decrypted = self._decrypt_data(content)
            if is_request:
                flow.metadata['decrypted_request'] = decrypted
                flow.comment += 'request data:\n'
            else:
                flow.metadata['decrypted_response'] = decrypted
                flow.comment += 'response data:\n'
            flow.comment += decrypted

    def request(self, flow: http.HTTPFlow) -> None:
        self._process_flow(flow, is_request=True)

    def response(self, flow: http.HTTPFlow) -> None:
        self._process_flow(flow, is_request=False)

    def reEncryptResponse(self, flow: http.HTTPFlow) -> None:
        """将解密后的响应重新加密为AES密文并更新响应内容"""
        if not self.aes_key:
            ctx.log.error("Re-encrypt failed: AES key not configured!")
            return

        # 获取解密后的明文
        decrypted = flow.metadata.get('decrypted_response', None)
        if not decrypted:
            ctx.log.error("No decrypted response data found in metadata!")
            return

        try:
            # 生成新的随机盐(32字节)和IV(16字节)
            salt = os.urandom(32)
            iv = os.urandom(16)

            # 生成密钥(PBKDF2参数需与解密端完全一致)
            key = PBKDF2(
                password=self.aes_key,
                salt=salt,
                dkLen=32,
                count=10000,
                hmac_hash_module=SHA1
            )

            # 执行加密流程
            data_bytes = decrypted.encode('utf-8', errors='replace')
            padded_data = pad(data_bytes, AES.block_size)  # PKCS7填充
            cipher = AES.new(key, AES.MODE_CBC, iv)
            ciphertext = cipher.encrypt(padded_data)

            # 组装新密文格式: salt(32) + iv(16) + ciphertext
            new_encrypted = salt + iv + ciphertext

            # 更新响应内容
            flow.response.content = new_encrypted
            flow.response.headers.pop('Content-Length', None)  # 清除长度头

            ctx.log.info("Response re-encrypted successfully")

        except Exception as e:
            ctx.log.error(f"Re-encryption failed: {str(e)}")
            flow.response.content = b"[RE-ENCRYPTION ERROR]"


apiAesInstance = AesInterceptor()
