import importlib.util
import unittest


class TestDesktopDependencies(unittest.TestCase):
    def test_uvicorn_has_websocket_protocol_support(self):
        has_websocket_backend = (
            importlib.util.find_spec("websockets") is not None
            or importlib.util.find_spec("wsproto") is not None
        )

        self.assertTrue(
            has_websocket_backend,
            "The desktop backend needs websockets or wsproto installed; "
            "otherwise HTTP works but chat WebSocket connections fail.",
        )

    def test_pdf_reader_dependency_is_available(self):
        self.assertIsNotNone(
            importlib.util.find_spec("pypdf"),
            "The desktop backend needs pypdf to read PDF literature files.",
        )


if __name__ == "__main__":
    unittest.main()
