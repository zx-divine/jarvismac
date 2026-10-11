"""Native macOS SecItem API. Imported only on macOS; no plaintext fallback."""
import ctypes

SERVICE = "org.ash.jarvis"
NOT_FOUND = -25300
DUPLICATE = -25299

class MacKeychain:
    def __init__(self):
        self.cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.sec = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
        pointer = ctypes.c_void_p
        signatures = {
            "CFStringCreateWithCString": ([pointer, ctypes.c_char_p, ctypes.c_uint32], pointer),
            "CFDataCreate": ([pointer, pointer, ctypes.c_long], pointer),
            "CFDataGetLength": ([pointer], ctypes.c_long),
            "CFDataGetBytePtr": ([pointer], pointer),
            "CFDictionaryCreateMutable": ([pointer, ctypes.c_long, pointer, pointer], pointer),
            "CFDictionarySetValue": ([pointer, pointer, pointer], None),
            "CFRelease": ([pointer], None),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.cf, name)
            fn.argtypes, fn.restype = args, result
        for name, args in {"SecItemCopyMatching": [pointer, ctypes.POINTER(pointer)], "SecItemAdd": [pointer, pointer], "SecItemUpdate": [pointer, pointer], "SecItemDelete": [pointer]}.items():
            fn = getattr(self.sec, name)
            fn.argtypes, fn.restype = args, ctypes.c_int32

    def constant(self, name, cf=False):
        return ctypes.c_void_p.in_dll(self.cf if cf else self.sec, name).value

    def query(self, account=None, data=None, returning=False):
        # Callback structs are referenced by address, not by their first field.
        keys = ctypes.addressof(ctypes.c_byte.in_dll(self.cf, "kCFTypeDictionaryKeyCallBacks"))
        values = ctypes.addressof(ctypes.c_byte.in_dll(self.cf, "kCFTypeDictionaryValueCallBacks"))
        result = self.cf.CFDictionaryCreateMutable(None, 0, keys, values)
        if not result:
            raise RuntimeError("Could not allocate Keychain query.")
        self.cf.CFDictionarySetValue(result, self.constant("kSecClass"), self.constant("kSecClassGenericPassword"))
        try:
            for key, value in (("kSecAttrService", SERVICE), ("kSecAttrAccount", account)):
                if value is not None:
                    string = self.cf.CFStringCreateWithCString(None, value.encode("utf-8"), 0x08000100)
                    try:
                        self.cf.CFDictionarySetValue(result, self.constant(key), string)
                    finally:
                        self.cf.CFRelease(string)
            if data is not None:
                buffer = ctypes.create_string_buffer(data)
                value = self.cf.CFDataCreate(None, buffer, len(data))
                try:
                    self.cf.CFDictionarySetValue(result, self.constant("kSecValueData"), value)
                finally:
                    self.cf.CFRelease(value)
            if returning:
                self.cf.CFDictionarySetValue(result, self.constant("kSecReturnData"), self.constant("kCFBooleanTrue", cf=True))
                self.cf.CFDictionarySetValue(result, self.constant("kSecMatchLimit"), self.constant("kSecMatchLimitOne"))
            return result
        except Exception:
            self.cf.CFRelease(result)
            raise

    @staticmethod
    def check(status):
        if status != 0:
            raise RuntimeError(f"macOS Keychain returned OSStatus {status}. Unlock your Keychain or approve JARVIS access in macOS; no plaintext fallback is used.")

    def get(self, account):
        query = self.query(account, returning=True)
        result = ctypes.c_void_p()
        try:
            status = self.sec.SecItemCopyMatching(query, ctypes.byref(result))
            if status == NOT_FOUND:
                return ""
            self.check(status)
            try:
                return ctypes.string_at(self.cf.CFDataGetBytePtr(result), self.cf.CFDataGetLength(result)).decode("utf-8")
            finally:
                self.cf.CFRelease(result)
        finally:
            self.cf.CFRelease(query)

    def set(self, account, secret):
        item = self.query(account, secret.encode("utf-8"))
        try:
            status = self.sec.SecItemAdd(item, None)
            if status == DUPLICATE:
                match = self.query(account)
                try:
                    # Update attributes must contain value data only.
                    keys = ctypes.addressof(ctypes.c_byte.in_dll(self.cf, "kCFTypeDictionaryKeyCallBacks"))
                    values = ctypes.addressof(ctypes.c_byte.in_dll(self.cf, "kCFTypeDictionaryValueCallBacks"))
                    update = self.cf.CFDictionaryCreateMutable(None, 0, keys, values)
                    buffer = ctypes.create_string_buffer(secret.encode("utf-8"))
                    data = self.cf.CFDataCreate(None, buffer, len(secret.encode("utf-8")))
                    try:
                        self.cf.CFDictionarySetValue(update, self.constant("kSecValueData"), data)
                        status = self.sec.SecItemUpdate(match, update)
                    finally:
                        self.cf.CFRelease(data)
                        self.cf.CFRelease(update)
                finally:
                    self.cf.CFRelease(match)
            self.check(status)
        finally:
            self.cf.CFRelease(item)

    def delete(self, account=None):
        query = self.query(account)
        try:
            status = self.sec.SecItemDelete(query)
            if status != NOT_FOUND:
                self.check(status)
        finally:
            self.cf.CFRelease(query)
