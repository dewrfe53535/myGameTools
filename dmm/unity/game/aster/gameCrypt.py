# 部分代码与注释由ai生成，可能会有手动修改但注释没改的地方
import base64
import os
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA1,SHA256
from Crypto.Util.Padding import pad, unpad

class AESCryptoHandler:
    def __init__(self, password=None, salt=None, iterations=1001,iv =None):
        """
        初始化AES加密处理器
        
        Args:
            password (bytes, optional): 用于派生密钥的密码
            salt (bytes, optional): 用于派生密钥的盐值
            iterations (int, optional): PBKDF2密钥派生的迭代次数
        """
        self.iterations = iterations
        
        if password is None:
            self._password = b'1111111111111111'
        else:
            self._password = password
            
        if salt is None:
            self._salt = b'1111111111111111'
        else:
            self._salt = salt
            
        # 派生AES密钥
        self.key = PBKDF2(self._password, self._salt, 16, count=self.iterations, hmac_hash_module=SHA1)
        if isinstance(iv,str):
            iv= iv.encode()        
        self.iv = iv
    
    @classmethod
    def decryptAndCreate(cls, base64_string, iterations=1001):
        """
        从base64编码的加密数据创建AESCryptoHandler实例并解密数据
        
        Args:
            base64_string (str): base64编码的加密数据
            iterations (int, optional): PBKDF2迭代次数
            
        Returns:
            tuple: (AESCryptoHandler实例, 解密后的字符串)
        """
        # 解码Base64数据
        raw_data = base64.b64decode(base64_string)
        
        # 从原始数据中提取各部分
        iv_reversed = raw_data[:16]
        iv = bytes(reversed(iv_reversed))  # 反转回正确的IV
        
        pass_reversed = raw_data[16:32]
        password = bytes(reversed(pass_reversed))  # 反转回正确的密码
        
        salt_reversed = raw_data[-16:]
        salt = bytes(reversed(salt_reversed))  # 反转回正确的盐值
        
        # 创建实例
        instance = cls(password=password, salt=salt, iterations=iterations,iv=iv)
        
        # 加密的负载在中间
        encrypted_payload = raw_data[32:-16]
        
        # 解密数据
        decrypted_data = instance.decrypt(encrypted_payload)
        
        return instance, decrypted_data
    
    def encrypt(self, data):
        """
        加密数据
        
        Args:
            data (bytes): 要加密的数据
            
        Returns:
            bytes: 加密后的数据
        """
        if not isinstance(data, bytes):
            raise TypeError("输入数据必须是bytes类型")
            
        # 生成IV（如果尚未设置）
        if self.iv is None:
            self.iv = os.urandom(16)
            
        # 创建AES密码器
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        
        # 使用PyCryptodome提供的pad函数进行PKCS7填充
        padded_data = pad(data, AES.block_size)
        
        # 加密数据
        encrypted_data = cipher.encrypt(padded_data)
        
        return encrypted_data
    
    def encrypt_base64(self, data):
        """
        加密数据并返回base64编码
        
        Args:
            data (bytes): 要加密的数据
            
        Returns:
            str: base64编码的加密数据
        """
        encrypted = self.encrypt(data)
        return base64.b64encode(encrypted).decode('utf-8')
    
    def encryptAndCreate(self, data):
        """
        加密数据并创建可被decryptAndCreate解密的格式
        
        Args:
            data (bytes): 要加密的数据
            
        Returns:
            str: base64编码的组合数据（可被decryptAndCreate方法解密）
        """
        if not isinstance(data, bytes):
            raise TypeError("输入数据必须是bytes类型")
            
        # 确保IV已生成
        if self.iv is None:
            self.iv = os.urandom(16)
            
        # 加密数据
        encrypted_payload = self.encrypt(data)
        
        # 按照指定格式组装数据
        iv_reversed = bytes(reversed(self.iv))
        pass_reversed = bytes(reversed(self.password))
        salt_reversed = bytes(reversed(self.salt))
        
        # 组合格式: [反转的IV][反转的密码][加密负载][反转的盐值]
        combined_data = iv_reversed + pass_reversed + encrypted_payload + salt_reversed
        
        # Base64编码
        return base64.b64encode(combined_data).decode('utf-8')
    
    def decrypt(self, data, iv_value=None):
        """
        解密数据
        
        Args:
            data: 要解密的数据，可以是base64编码的字符串或直接的字节数据
            iv_value (bytes, optional): 可选的IV值用于解密，不会覆盖self.iv
            
        Returns:
            str: 解密后的UTF-8字符串
        """
        # 处理base64输入
        if isinstance(data, str):
            try:
                data = base64.b64decode(data)
            except:
                raise ValueError("无效的base64字符串")
        
        # 确定使用哪个IV
        iv_to_use = iv_value if iv_value is not None else self.iv
                
        # 确保IV已设置
        if iv_to_use is None:
            raise ValueError("解密前必须设置IV或提供iv_value参数")
            
        # 创建解密器
        cipher = AES.new(self.key, AES.MODE_CBC, iv_to_use)
        
        # 解密数据
        decrypted_padded_data = cipher.decrypt(data)
        # 使用PyCryptodome提供的unpad函数移除PKCS7填充
        try:
            decrypted_data = unpad(decrypted_padded_data, AES.block_size)
        except ValueError as e:
            raise ValueError(f"解密填充错误: {e}")
        
        # 将字节转换为UTF-8字符串
        return decrypted_data.decode('utf-8')

    @property
    def salt(self):
        return self._salt
    
    @salt.setter
    def salt(self, value):
        self._salt = value
        self.key = PBKDF2(self.password, self.salt, 16, count=self.iterations, hmac_hash_module=SHA1)
    
    @property
    def password(self):
        return self._password
    
    @password.setter
    def password(self, value):
        self._password = value
        self.key = PBKDF2(self.password, self.salt, 16, count=self.iterations, hmac_hash_module=SHA1)
        
def decrypt_by_master_data(encrypted_bytes, password, iterations=1010):
    """
    Decrypt data that has been encrypted with AES.
    
    Args:
        encrypted_bytes (bytes): The encrypted data
        password (str): The password used for decryption
        iterations (int): Number of iterations for key derivation
        
    Returns:
        bytes: Decrypted data
    """
    # Extract initialization vector (IV) - first 16 bytes
    iv = encrypted_bytes[16:32]
    
    # Extract the salt - after the first 32 bytes, excluding the last 16 bytes
    data_length = len(encrypted_bytes[32:])
    salt = encrypted_bytes[32:][data_length-16:]
    
    # Extract the encrypted data - everything after 32 bytes, excluding the last 16 bytes (salt)
    encrypted_data = encrypted_bytes[32:data_length+16]
    
    # Convert password to bytes if it's a string
    if isinstance(password, str):
        password = password.encode('utf-8')
    
    # Derive key using PBKDF2 with SHA256
    key = PBKDF2(
        password=password,
        salt=salt,
        dkLen=16,  # AES-128 uses 16-byte key
        count=iterations,
        hmac_hash_module=SHA256
    )
    
    # Create AES cipher in CBC mode with PKCS7 padding
    cipher = AES.new(key, AES.MODE_CBC, iv)
    
    # Decrypt the data
    decrypted_data = unpad(cipher.decrypt(encrypted_data), AES.block_size)
    
    return decrypted_data