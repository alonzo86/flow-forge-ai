from io import BytesIO
import json
from unittest.mock import Mock, patch

from flow_forge_ai.replay import _ReplayRequest
from flow_forge_ai.runtime import _Runtime, _RuntimeListener, _RuntimeRequestHandler
from flow_forge_ai.sinks.memory_sink import MemorySink
import pytest
from conftest import StringContaining, runs, steps


@pytest.fixture
def mock_runtime_owner():
    runtime_mock = Mock(spec=_Runtime)
    runtime_mock.replay_manager = Mock()
    runtime_mock.replay_manager.list_runs.return_value = runs
    runtime_mock.replay_manager.list_steps.return_value = steps
    runtime_mock.replay_manager.request_replay.side_effect = lambda run_id, start_step_id: _ReplayRequest(workflow_id="workflow_1", run_id=run_id, start_step_id=start_step_id)
    runtime_mock.replay_manager.get_replay_request.return_value = _ReplayRequest(workflow_id="workflow_1", run_id="r1", start_step_id=steps[0].id)
    runtime_mock.replay_manager.get_step.side_effect = lambda workflow_id, step_id: next((step for step in steps if step.id == step_id), None)
    return runtime_mock


@pytest.fixture
def mock_server(mocker, mock_runtime_owner):
    mocked_server = Mock()
    mocked_server.server_address = ("test_host", 1234)
    mocked_server.serve_forever = lambda: print("Mock server running...")
    server = mocker.patch("flow_forge_ai.runtime.ThreadingHTTPServer", autospec=True)
    server.return_value = mocked_server
    server.return_value.runtime = mock_runtime_owner
    return server


class TestRuntime:
    def test_runtime_initialization(self):
        rt = _Runtime()
        assert rt is not None

    @patch("flow_forge_ai.runtime._RuntimeListener")
    def test_runtime_start_listener(self, MockListener):
        MockListener.return_value = Mock()
        rt = _Runtime()
        rt.start_listener(resource_handler=Mock(),
                          host="localhost",
                          port=8080)
        assert rt._listener is not None
        rt.close()
        assert rt._listener is None

    def test_runtime_start_listener_error(self):
        rt = _Runtime()
        with pytest.raises(ValueError):
            rt.start_listener(resource_handler=Mock())

    def test_runtime_load_sink(self):
        rt = _Runtime()
        mem = MemorySink()
        rt.load_sink(mem)
        assert mem in rt._router._sink.sinks

    def test_runtime_load_instrumentor(self):
        rt = _Runtime()
        instr = Mock()
        rt.load_instrumentor(instr)
        assert instr in rt._instrumentors
        instr.install.assert_called_once()

    def test_runtime_uninstrument_all(self):
        rt = _Runtime()
        instr1 = Mock()
        instr2 = Mock()
        rt.load_instrumentor(instr1)
        rt.load_instrumentor(instr2)
        rt.uninstrument_all()
        instr1.uninstall.assert_called_once()
        instr2.uninstall.assert_called_once()


class TestRuntimeListener:

    def test_runtime_request_handler_initialization(self, mock_runtime_owner, mock_server, mocker):
        Thread = mocker.patch("threading.Thread")
        rt_listener = _RuntimeListener(runtime_owner=mock_runtime_owner,
                                       host="test_host",
                                       port=1234)
        rt_listener.start()
        _, kwargs = Thread.call_args
        
        assert kwargs["target"] == mock_server.return_value.serve_forever
        rt_listener.stop()


class TestRuntimeRequestHandler:

    def test_log_message(self, mock_server):
        request_mock = Mock()
        raw_http = b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"
        rfile = BytesIO(raw_http)
        request_mock.makefile.return_value = rfile
        handler = _RuntimeRequestHandler(request=request_mock, client_address=None, server=mock_server.return_value)
        with patch.object(handler, 'log_message') as mock_log:
            handler.log_message("Test message: %s", "arg1")
            mock_log.assert_called_once_with("Test message: %s", "arg1")

    def test_do_GET_api_replay(self, mock_server):
        request_mock = Mock()
        raw_http = b"GET /api/runs/r1/replay HTTP/1.1\r\nHost: localhost\r\n\r\n"
        expected_response = _ReplayRequest(workflow_id="workflow_1", run_id="r1", start_step_id=steps[0].id).to_dict()
        rfile = BytesIO(raw_http)
        request_mock.makefile.return_value = rfile
        handler = _RuntimeRequestHandler(request=request_mock, client_address=None, server=mock_server.return_value)
        with patch.object(handler, '_send_json') as mock_send_json, \
             patch.object(handler, 'send_header') as mock_send_header, \
             patch.object(handler, 'end_headers') as mock_end_headers, \
             patch.object(handler, 'wfile', new_callable=BytesIO) as mock_wfile:
            handler.do_GET()
            mock_send_json.assert_called_once_with(200, expected_response)

    def test_do_GET_api_runs(self, mock_server):
        request_mock = Mock()
        raw_http = b"GET /api/runs?workflow_id=12 HTTP/1.1\r\nHost: localhost\r\n\r\n"
        expected_response = [run.to_dict() for run in runs]
        rfile = BytesIO(raw_http)
        request_mock.makefile.return_value = rfile
        handler = _RuntimeRequestHandler(request=request_mock, client_address=None, server=mock_server.return_value)
        with patch.object(handler, '_send_json') as mock_send_json, \
             patch.object(handler, 'send_header') as mock_send_header, \
             patch.object(handler, 'end_headers') as mock_end_headers, \
             patch.object(handler, 'wfile', new_callable=BytesIO) as mock_wfile:
            handler.do_GET()
            mock_send_json.assert_called_once_with(200, expected_response)

    def test_do_GET_api_steps(self, mock_server):
        request_mock = Mock()
        raw_http = b"GET /api/steps?run_id=12 HTTP/1.1\r\nHost: localhost\r\n\r\n"
        expected_response = [step.to_dict() for step in steps]
        rfile = BytesIO(raw_http)
        request_mock.makefile.return_value = rfile
        handler = _RuntimeRequestHandler(request=request_mock, client_address=None, server=mock_server.return_value)
        with patch.object(handler, '_send_json') as mock_send_json, \
             patch.object(handler, 'send_header') as mock_send_header, \
             patch.object(handler, 'end_headers') as mock_end_headers, \
             patch.object(handler, 'wfile', new_callable=BytesIO) as mock_wfile:
            handler.do_GET()
            mock_send_json.assert_called_once_with(200, expected_response)

    def test_do_Delete_api_replay(self, mock_server):
        request_mock = Mock()
        raw_http = b"DELETE /api/runs/r1/replay HTTP/1.1\r\nHost: localhost\r\n\r\n"
        expected_response = _ReplayRequest(workflow_id="workflow_1", run_id="r1", start_step_id=steps[0].id).to_dict()
        rfile = BytesIO(raw_http)
        request_mock.makefile.return_value = rfile
        handler = _RuntimeRequestHandler(request=request_mock, client_address=None, server=mock_server.return_value)
        with patch.object(handler, '_send_json') as mock_send_json, \
             patch.object(handler, 'send_header') as mock_send_header, \
             patch.object(handler, 'end_headers') as mock_end_headers, \
             patch.object(handler, 'wfile', new_callable=BytesIO) as mock_wfile:
            handler.do_DELETE()
            mock_send_json.assert_called_once_with(202, expected_response)

    def test_do_POST_api_replay_with_body(self, mock_server):
        request_mock = Mock()
        body = json.dumps({"start_step_id": "step-2"}).encode('utf-8')
        raw_http = b"POST /api/runs/r1/replay HTTP/1.1\r\nHost: localhost\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body)
        expected_response = _ReplayRequest(workflow_id="workflow_1", run_id="r1", start_step_id="step-2").to_dict()
        rfile = BytesIO(raw_http)
        request_mock.makefile.return_value = rfile

        with patch.object(_RuntimeRequestHandler, '_send_json') as mock_send_json:
            handler = _RuntimeRequestHandler(request=request_mock, client_address=None, server=mock_server.return_value)
            mock_send_json.assert_called_once_with(202, expected_response)
    
    def test_do_POST_api_replay_invalid_json(self, mock_server):
        request_mock = Mock()
        body = b"{invalid_json}"
        raw_http = b"POST /api/runs/r1/replay HTTP/1.1\r\nHost: localhost\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body)
        rfile = BytesIO(raw_http)
        request_mock.makefile.return_value = rfile
        with patch.object(_RuntimeRequestHandler, 'send_error') as mock_send_error:
            handler = _RuntimeRequestHandler(request=request_mock, client_address=None, server=mock_server.return_value)
            mock_send_error.assert_called_once_with(400, StringContaining("Expecting property name enclosed in double quotes"))
