from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad
import zlib
import base64
from itsdangerous import base64_encode

def response_encrypt(data):
    zlibobj  = zlib.compressobj(level=1,wbits=15)
    data =  zlibobj.compress(data.encode('utf-8'))
    data +=  zlibobj.flush()
    data = pad(data,16)
    iv  = get_random_bytes(16)
    iv_pretrans = iv.hex().upper()
    trans_iv = ''
    for a in range(len(iv_pretrans)):
        trans_iv += reponseivtable[c_iv.index(iv_pretrans[a])]
    trans_iv = trans_iv.encode('ascii')
    data = AES.new(reponsekey, AES.MODE_CBC, iv).encrypt(data)
    data = base64.b64encode(data)
    return base64.b64encode(trans_iv+data).decode()

def response_decrypt(data):
    e = base64.b64decode(data)
    iv_trans = e[:32].decode('ascii')
    iv = ''
    for a in range(len(iv_trans)):
        iv += '{:x}'.format(reponseivtable.index(iv_trans[a]))
    iv = bytes.fromhex(iv)
    data = base64.b64decode(e[32:])
    c = unpad(AES.new(reponsekey, AES.MODE_CBC, iv).decrypt(data),16)
    h = zlib.decompress(c).decode()
    return h

def request_decrypt(data):
    e = base64.b64decode(data)
    iv = bytes.fromhex(e[:32].decode())
    data = base64.b64decode(e[32:])
    c = unpad(AES.new(requestkey, AES.MODE_CBC, iv).decrypt(data),16).decode()
    return c
    
def request_encrypt(data):
    data = pad(data,16)
    iv = get_random_bytes(16)
    iv_hex = iv.hex().upper()
    data  = AES.new(requestkey, AES.MODE_CBC, iv).encrypt(data)
    data = base64.b64encode(data)
    return base64_encode(iv_hex+data).decode()
