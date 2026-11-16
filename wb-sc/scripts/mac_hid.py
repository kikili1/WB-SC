"""macOS HIDAPI backend. All native calls run in a bounded worker process."""
from contextlib import contextmanager
from dataclasses import dataclass
import json
import math
from pathlib import Path
import queue
import subprocess
import sys
import threading


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
    manufacturer: str
    output_reports: dict


def report_lengths(descriptor):
    """Return Input/Output/Feature byte lengths by report ID (including ID byte)."""
    raw = bytes(descriptor)
    if not raw or len(raw) > 4096:
        raise ValueError('Invalid HID report descriptor length')
    state = {7: 0, 8: 0, 9: 0}  # Report Size, ID, Count
    stack, bits = [], {8: {}, 9: {}, 11: {}}
    pos = 0
    while pos < len(raw):
        prefix = raw[pos]
        pos += 1
        if prefix == 0xFE:
            if pos + 2 > len(raw):
                raise ValueError('Truncated HID long item')
            size = raw[pos]
            pos += 2
            if pos + size > len(raw):
                raise ValueError('Truncated HID long item')
            pos += size
            continue
        size = (0, 1, 2, 4)[prefix & 3]
        if pos + size > len(raw):
            raise ValueError('Truncated HID item')
        value = int.from_bytes(raw[pos:pos + size], 'little')
        pos += size
        kind, tag = (prefix >> 2) & 3, prefix >> 4
        if kind == 1:
            if tag in state:
                if tag == 8 and not 1 <= value <= 255:
                    raise ValueError('Invalid HID report ID')
                state[tag] = value
            elif tag == 10:
                stack.append(state.copy())
            elif tag == 11:
                if not stack:
                    raise ValueError('Unbalanced HID Pop')
                state = stack.pop()
        elif kind == 0 and tag in bits:
            count = state[7] * state[9]
            if not count:
                raise ValueError('Missing HID Report Size/Count')
            rid = state[8]
            bits[tag][rid] = bits[tag].get(rid, 0) + count
            if bits[tag][rid] > 65535 * 8:
                raise ValueError('HID report too large')
    if stack or not any(bits.values()):
        raise ValueError('Incomplete HID descriptor')
    return {tag: {str(rid): (n + 7) // 8 + (1 if rid or tag != 8 else 0)
                  for rid, n in reports.items()} for tag, reports in bits.items()}


def load_hid():
    try:
        import hid
    except ImportError as exc:
        raise OSError('macOS hardware requires hidapi: run this Python with '
                      '-m pip install hidapi==0.15.0') from exc
    if not hasattr(hid, 'device') or not hasattr(hid.device, 'get_report_descriptor'):
        raise OSError('Wrong/old hid package; install hidapi==0.15.0 in the Hook Python')
    return hid


class Worker:
    def __init__(self):
        self.process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--worker'],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding='utf-8')
        self.replies = queue.Queue()
        self.thread = threading.Thread(target=self._receive, daemon=True)
        self.thread.start()

    def _receive(self):
        try:
            for line in self.process.stdout:
                self.replies.put(line)
        finally:
            self.replies.put(None)

    def request(self, operation, timeout=3, **params):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('HID timeout must be positive and finite')
        try:
            self.process.stdin.write(json.dumps(dict(operation=operation, **params)) + '\n')
            self.process.stdin.flush()
            line = self.replies.get(timeout=timeout)
            if line is None:
                raise OSError('macOS HID worker exited')
            response = json.loads(line)
            if 'error' in response:
                raise OSError(response['error'])
            return response['result']
        except queue.Empty as exc:
            self.close()
            raise TimeoutError('macOS HID operation timed out; result may be unknown') from exc
        except (BrokenPipeError, ValueError):
            self.close()
            raise

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process.wait(timeout=2)
        self.thread.join(timeout=1)
        self.process.stdin.close()
        self.process.stdout.close()


_readers = {}


def enumerate_hid_devices():
    worker = Worker()
    try:
        return [HidDeviceInfo(**item) for item in worker.request('enumerate', timeout=2)]
    finally:
        worker.close()


@contextmanager
def open_reader(info):
    if info.path in _readers:
        raise OSError('HID reader already open')
    worker = Worker()
    try:
        # Leave time for enumeration/write/cleanup inside WorkBuddy's 6-second Hook limit.
        worker.request('open', timeout=2, path=info.path)
        _readers[info.path] = worker

        def read(timeout):
            if timeout <= 0:
                return None
            return bytes(worker.request('read', timeout=timeout + 0.5,
                                        length=info.input_report_length,
                                        milliseconds=max(1, math.ceil(timeout * 1000)))) or None
        yield read
    finally:
        _readers.pop(info.path, None)
        worker.close()


def write_report(info, payload, timeout):
    if not payload:
        raise ValueError('Empty HID output')
    length = info.output_reports.get(str(payload[0]))
    if length is None or len(payload) > length:
        raise ValueError('Output report ID/length does not match HID descriptor')
    data = bytes(payload) + bytes(length - len(payload))
    worker = _readers.get(info.path)
    owned = worker is None
    if owned:
        worker = Worker()
    try:
        if owned:
            worker.request('open', timeout=timeout, path=info.path)
        worker.request('write', timeout=timeout, data=data.hex())
    finally:
        if owned:
            worker.close()


def enumerate_native(hid):
    devices = []
    seen = set()
    for item in hid.enumerate():
        if item['usage_page'] not in (0xFF01, 0xFF02) or item['path'] in seen:
            continue
        seen.add(item['path'])
        device = hid.device()
        try:
            device.open_path(item['path'])
            lengths = report_lengths(device.get_report_descriptor())
        except (OSError, ValueError) as exc:
            raise OSError('Cannot inspect HID %r: %s (check device access/permissions)' %
                          (item['path'], exc)) from exc
        finally:
            device.close()
        devices.append(dict(path=item['path'].hex(), vendor_id=item['vendor_id'],
                            product_id=item['product_id'], version=item['release_number'],
                            usage_page=item['usage_page'], usage=item['usage'],
                            input_report_length=max(lengths[8].values(), default=0),
                            output_report_length=max(lengths[9].values(), default=0),
                            feature_report_length=max(lengths[11].values(), default=0),
                            manufacturer=item.get('manufacturer_string') or '',
                            output_reports=lengths[9]))
    return devices


def serve():
    device = None
    lengths = None
    try:
        for line in sys.stdin:
            try:
                args = json.loads(line)
                operation = args['operation']
                hid = load_hid()
                if operation == 'enumerate':
                    result = enumerate_native(hid)
                elif operation == 'open':
                    if device is not None:
                        raise OSError('HID device already open')
                    device = hid.device()
                    device.open_path(bytes.fromhex(args['path']))
                    lengths = report_lengths(device.get_report_descriptor())
                    result = None
                elif operation == 'read' and device is not None:
                    result = device.read(args['length'], args['milliseconds'])
                elif operation == 'write' and device is not None:
                    data = bytes.fromhex(args['data'])
                    if not data or lengths[9].get(str(data[0])) != len(data):
                        raise ValueError('Output does not match current HID descriptor')
                    if device.write(data) != len(data):
                        raise OSError('Short HID write; execution result unknown')
                    result = None
                else:
                    raise ValueError('Invalid HID worker operation')
                response = {'result': result}
            except Exception as exc:
                response = {'error': str(exc)}
            print(json.dumps(response), flush=True)
    finally:
        if device is not None:
            device.close()


if __name__ == '__main__' and sys.argv[1:] == ['--worker']:
    serve()
