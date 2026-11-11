from __future__ import annotations

import ctypes
import math
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass


DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

HIDP_STATUS_SUCCESS = 0x00110000


setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


class SP_DEVICE_INTERFACE_DETAIL_DATA_W(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("DevicePath", wintypes.WCHAR * 1),
    ]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", wintypes.ULONG),
        ("VendorID", wintypes.USHORT),
        ("ProductID", wintypes.USHORT),
        ("VersionNumber", wintypes.USHORT),
    ]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", wintypes.USHORT),
        ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT),
        ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]


setupapi.SetupDiGetClassDevsW.argtypes = [
    ctypes.POINTER(GUID),
    wintypes.LPCWSTR,
    wintypes.HWND,
    wintypes.DWORD,
]
setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.POINTER(GUID),
    wintypes.DWORD,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
]
setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
hid.HidD_GetHidGuid.restype = None
hid.HidD_GetAttributes.argtypes = [wintypes.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetAttributes.restype = wintypes.BOOL
hid.HidD_GetManufacturerString.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
hid.HidD_GetManufacturerString.restype = wintypes.BOOL
hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_GetPreparsedData.restype = wintypes.BOOL
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidD_FreePreparsedData.restype = wintypes.BOOL
hid.HidD_SetOutputReport.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
hid.HidD_SetOutputReport.restype = wintypes.BOOL
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
hid.HidP_GetCaps.restype = wintypes.LONG

kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.ReadFile.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
kernel32.ReadFile.restype = wintypes.BOOL
kernel32.WriteFile.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
kernel32.WriteFile.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.CancelIoEx.restype = wintypes.BOOL


@dataclass(frozen=True)
class HidDeviceInfo:
    path: str
    vendor_id: int
    product_id: int
    version: int
    usage_page: int
    usage: int
    input_report_length: int
    output_report_length: int
    feature_report_length: int
    manufacturer: str = ""

class HidOpenError(OSError):
    pass


def _raise_last_error(message: str) -> None:
    err = ctypes.get_last_error()
    raise HidOpenError(f"{message} (WinError {err})")


def get_hid_guid() -> GUID:
    guid = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    return guid


def _open_handle(path: str, read: bool = True, write: bool = True, flags: int = 0) -> int:
    access = 0
    if read:
        access |= GENERIC_READ
    if write:
        access |= GENERIC_WRITE
    handle = kernel32.CreateFileW(
        path,
        access,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        flags,
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        _raise_last_error("Cannot open HID device")
    return int(handle)


def _get_caps(handle: int) -> HIDP_CAPS:
    preparsed = ctypes.c_void_p()
    if not hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)):
        _raise_last_error("Cannot get HID preparsed data")
    try:
        caps = HIDP_CAPS()
        status = hid.HidP_GetCaps(preparsed, ctypes.byref(caps))
        if status != HIDP_STATUS_SUCCESS:
            raise HidOpenError(f"Cannot read HID caps (status 0x{status:08X})")
        return caps
    finally:
        hid.HidD_FreePreparsedData(preparsed)


def _get_attributes(handle: int) -> HIDD_ATTRIBUTES:
    attrs = HIDD_ATTRIBUTES()
    attrs.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
    if not hid.HidD_GetAttributes(handle, ctypes.byref(attrs)):
        _raise_last_error("Cannot get HID attributes")
    return attrs


def enumerate_hid_devices() -> list[HidDeviceInfo]:
    guid = get_hid_guid()
    info_set = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid),
        None,
        None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE,
    )
    if info_set == INVALID_HANDLE_VALUE:
        _raise_last_error("Cannot enumerate HID devices")

    devices: list[HidDeviceInfo] = []
    try:
        index = 0
        while True:
            iface = SP_DEVICE_INTERFACE_DATA()
            iface.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
            ok = setupapi.SetupDiEnumDeviceInterfaces(
                info_set, None, ctypes.byref(guid), index, ctypes.byref(iface)
            )
            if not ok:
                if ctypes.get_last_error() != 259:
                    _raise_last_error("HID enumeration failed")
                break

            required = wintypes.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                info_set, ctypes.byref(iface), None, 0, ctypes.byref(required), None
            )
            detail_buf = ctypes.create_string_buffer(required.value)
            detail = ctypes.cast(detail_buf, ctypes.POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA_W))
            detail.contents.cbSize = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if setupapi.SetupDiGetDeviceInterfaceDetailW(
                info_set,
                ctypes.byref(iface),
                detail,
                required.value,
                None,
                None,
            ):
                path = ctypes.wstring_at(
                    ctypes.addressof(detail.contents)
                    + SP_DEVICE_INTERFACE_DETAIL_DATA_W.DevicePath.offset
                )
                handle = None
                try:
                    handle = _open_handle(path, read=False, write=False)
                    attrs = _get_attributes(handle)
                    caps = _get_caps(handle)
                    devices.append(
                        HidDeviceInfo(
                            path=path,
                            vendor_id=int(attrs.VendorID),
                            product_id=int(attrs.ProductID),
                            version=int(attrs.VersionNumber),
                            usage_page=int(caps.UsagePage),
                            usage=int(caps.Usage),
                            input_report_length=int(caps.InputReportByteLength),
                            output_report_length=int(caps.OutputReportByteLength),
                            feature_report_length=int(caps.FeatureReportByteLength),
                        )
                    )
                except OSError:
                    pass
                finally:
                    if handle is not None:
                        kernel32.CloseHandle(handle)
            index += 1
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(info_set)
    return devices


class OVERLAPPED(ctypes.Structure):
    _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD),
                ('hEvent', wintypes.HANDLE)]


kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED),
                                      ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
kernel32.GetOverlappedResult.restype = wintypes.BOOL


@contextmanager
def open_reader(info):
    """Keep the HID input queue open before writing and between reads."""
    handle = _open_handle(info.path, read=True, write=False, flags=0x40000000)
    try:
        yield lambda timeout: _read_report(handle, info.input_report_length, timeout)
    finally:
        kernel32.CloseHandle(handle)


def read_report(info, timeout):
    with open_reader(info) as read:
        return read(timeout)


def _read_report(handle, length, timeout):
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('Invalid timeout')
    length = max(1, length)
    event = None
    pending = False
    overlap = OVERLAPPED()
    read = wintypes.DWORD()
    buf = (ctypes.c_ubyte * length)()
    try:
        event = kernel32.CreateEventW(None, True, False, None)
        if not event:
            _raise_last_error('Cannot create HID read event')
        overlap.hEvent = event
        ok = kernel32.ReadFile(handle, buf, length, ctypes.byref(read), ctypes.byref(overlap))
        if not ok:
            if ctypes.get_last_error() != 997:
                _raise_last_error('HID read failed')
            pending = True
            wait = kernel32.WaitForSingleObject(event, max(1, int(timeout * 1000)))
            if wait != 0:
                return None
            if not kernel32.GetOverlappedResult(handle, ctypes.byref(overlap), ctypes.byref(read), False):
                _raise_last_error('HID read completion failed')
            pending = False
        return bytes(buf[:read.value])
    finally:
        if pending:
            kernel32.CancelIoEx(handle, ctypes.byref(overlap))
            kernel32.GetOverlappedResult(handle, ctypes.byref(overlap), ctypes.byref(read), True)
        if event:
            kernel32.CloseHandle(event)


def write_report(info, payload, timeout):
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('Invalid timeout')
    if not payload or len(payload) > info.output_report_length:
        raise ValueError('Refusing to truncate HID report')
    data = payload + bytes(info.output_report_length - len(payload))
    handle = _open_handle(info.path, read=False, write=True, flags=0x40000000)
    event = None
    pending = False
    overlap = OVERLAPPED()
    written = wintypes.DWORD()
    buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    try:
        event = kernel32.CreateEventW(None, True, False, None)
        if not event:
            _raise_last_error('Cannot create HID write event')
        overlap.hEvent = event
        ok = kernel32.WriteFile(handle, buf, len(data), ctypes.byref(written), ctypes.byref(overlap))
        if not ok:
            if ctypes.get_last_error() != 997:
                _raise_last_error('HID write failed')
            pending = True
            wait = kernel32.WaitForSingleObject(event, max(1, int(timeout * 1000)))
            if wait == 258:
                raise TimeoutError('HID write timed out; no retry sent')
            if wait != 0:
                _raise_last_error('HID wait failed')
            if not kernel32.GetOverlappedResult(handle, ctypes.byref(overlap), ctypes.byref(written), False):
                _raise_last_error('HID write completion failed')
            pending = False
        if written.value != len(data):
            raise OSError('Incomplete HID write')
    finally:
        if pending:
            kernel32.CancelIoEx(handle, ctypes.byref(overlap))
            # Buffer and OVERLAPPED must survive until the cancelled operation completes.
            kernel32.GetOverlappedResult(handle, ctypes.byref(overlap), ctypes.byref(written), True)
        kernel32.CloseHandle(handle)
        if event:
            kernel32.CloseHandle(event)


