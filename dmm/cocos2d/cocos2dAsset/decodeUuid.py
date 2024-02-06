BASE64_KEYS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/='
BASE64_VALUES = bytearray(123)
for i in range(123):
    BASE64_VALUES[i] = 64
for i in range(64):
    BASE64_VALUES[ord(BASE64_KEYS[i])] = i
separator = '@'

HexChars = list('0123456789abcdef')
_t = ['', '', '', '']
UuidTemplate = _t + _t + ['-', *_t] + ['-', *_t] + ['-', *_t] + ['-', *_t] + _t + _t
Indices = [i for i, x in enumerate(UuidTemplate) if x != '-']


def decodeUuid(base64: str) -> str:
    strs = base64.split(separator)
    uuid = strs[0]
    if len(uuid) != 22:
        return base64

    UuidTemplate[0], UuidTemplate[1] = base64[0], base64[1]
    j = 2
    for i in range(2, 22, 2):
        lhs = BASE64_VALUES[ord(base64[i])]
        rhs = BASE64_VALUES[ord(base64[i + 1])]
        UuidTemplate[Indices[j]] = HexChars[lhs >> 2]
        UuidTemplate[Indices[j + 1]] = HexChars[((lhs & 3) << 2) | rhs >> 4]
        UuidTemplate[Indices[j + 2]] = HexChars[rhs & 0xF]
        j += 3

    return base64.replace(uuid, ''.join(UuidTemplate))
