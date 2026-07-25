import asyncio
from typing import Optional

from textual._xterm_parser import XTermParser
from textual.drivers import win32
from textual.drivers._writer_thread import WriterThread
from textual.drivers.windows_driver import WindowsDriver


SHIFT_PRESSED = 0x0010
VK_RETURN = 0x0D
KITTY_SHIFT_ENTER = "\x1b[13;2u"


def encode_console_key(key_event):
    if (
        int(key_event.wVirtualKeyCode) == VK_RETURN
        and int(key_event.dwControlKeyState) & SHIFT_PRESSED
    ):
        return KITTY_SHIFT_ENTER
    return key_event.uChar.UnicodeChar


class ModifierAwareEventMonitor(win32.EventMonitor):
    """Preserve Shift+Enter, which Textual's Windows monitor otherwise discards."""

    def run(self):
        exit_requested = self.exit_event.is_set
        parser = XTermParser(debug=win32.constants.DEBUG)

        try:
            read_count = win32.wintypes.DWORD(0)
            input_handle = win32.GetStdHandle(win32.STD_INPUT_HANDLE)
            max_events = 1024
            key_event_type = 0x0001
            resize_event_type = 0x0004
            input_records = (win32.INPUT_RECORD * max_events)()
            read_console_input = win32.KERNEL32.ReadConsoleInputW
            keys = []

            while not exit_requested():
                for event in parser.tick():
                    self.process_event(event)

                if win32.wait_for_handles([input_handle], 100) is None:
                    continue

                read_console_input(
                    input_handle,
                    win32.byref(input_records),
                    max_events,
                    win32.byref(read_count),
                )
                del keys[:]
                new_size: Optional[tuple[int, int]] = None

                for input_record in input_records[: read_count.value]:
                    if input_record.EventType == key_event_type:
                        key_event = input_record.Event.KeyEvent
                        if not key_event.bKeyDown:
                            continue
                        if key_event.dwControlKeyState and key_event.wVirtualKeyCode == 0:
                            continue
                        keys.append(encode_console_key(key_event))
                    elif input_record.EventType == resize_event_type:
                        size = input_record.Event.WindowBufferSizeEvent.dwSize
                        new_size = (size.X, size.Y)

                if keys:
                    text = "".join(keys).encode("utf-16", "surrogatepass").decode("utf-16")
                    for event in parser.feed(text):
                        self.process_event(event)
                if new_size is not None:
                    self.on_size_change(*new_size)
        except Exception as error:
            self.app.log.error("EVENT MONITOR ERROR", error)


class ModifierAwareWindowsDriver(WindowsDriver):
    def start_application_mode(self):
        loop = asyncio.get_running_loop()
        self._restore_console = win32.enable_application_mode()
        self._writer_thread = WriterThread(self._file)
        self._writer_thread.start()
        self.write("\x1b[?1049h")
        self._enable_mouse_support()
        self.write("\x1b[?25l")
        self.write("\033[?1004h")
        self.write("\x1b[>1u")
        self.flush()
        self._enable_bracketed_paste()
        self._event_thread = ModifierAwareEventMonitor(
            loop,
            self._app,
            self.exit_event,
            self.process_message,
        )
        self._event_thread.start()
