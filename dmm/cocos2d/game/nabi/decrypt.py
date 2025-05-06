import json
from config import *

def decrypt(data:str|bytes):
    if isinstance(data,str):
        data = data.encode()
    sig_len = len(Asign) 
    header_len = sig_len + 6
    rkey = Akey + data[sig_len:sig_len + 4]
    # rkey = Akey
    encrypted_data = data[header_len:]
    key_index = 0
    decrypted_data = bytearray(encrypted_data)
    for i in range(0,len(encrypted_data),3):
        decrypted_data[i] = encrypted_data[i] ^ rkey[key_index]
        key_index = (key_index + 1) % len(rkey)
    return decrypted_data

def decryptAndLoadJson(data:str|bytes):
    return json.loads(decrypt(data))
