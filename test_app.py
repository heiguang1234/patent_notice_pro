"""验证 API 上传、跨域和反代请求；不调用付费模型。"""
import json
import os
import threading
import unittest
import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.validation import check_quotes
from backend.services.drafting import generate_draft
from backend.services.formatting import format_notice
from backend.services.model_client import read_model_stream

class MockModel(BaseHTTPRequestHandler):
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert self.path == '/v1/chat/completions'
        assert '[申请文件 §1]' in request['messages'][1]['content']
        assert '[对比文件1 §1]' in request['messages'][1]['content']
        response = json.dumps({'choices': [{'message': {'content': '测试草稿 [申请文件 §1] [对比文件1 §1]'}}]}).encode()
        if request.get('stream'):
            response = ('data: ' + json.dumps({'choices': [{'delta': {'content': '测试草稿'}}]}) + '\n\n'
                        + 'data: ' + json.dumps({'choices': [{'delta': {}, 'finish_reason': 'stop'}]}) + '\n\n'
                        + 'data: [DONE]\n\n').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream' if request.get('stream') else 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)

class SmokeTest(unittest.TestCase):
    def test_model_stream_incomplete(self):
        raw = ('data: ' + json.dumps({'choices': [{'delta': {'content': '部分正文'}}]}) + '\n\n').encode()
        with self.assertRaisesRegex(ValueError, '提前中断'):
            read_model_stream(io.BytesIO(raw), lambda count: None)
        raw += ('data: ' + json.dumps({'choices': [{'delta': {}, 'finish_reason': 'length'}]}) + '\n\n').encode()
        with self.assertRaisesRegex(ValueError, '截断'):
            read_model_stream(io.BytesIO(raw), lambda count: None)

    def test_streaming_progress_and_result(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), MockModel)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with patch.dict(os.environ, {'API_BASE_URL': f'http://127.0.0.1:{server.server_port}/v1', 'MODEL': 'mock'}):
                with TestClient(app) as client:
                    response = client.post('/api/draft?stream=true', files=[
                        ('application', ('a.txt', '申请内容'.encode(), 'text/plain')),
                        ('comparison1', ('d.txt', '对比内容'.encode(), 'text/plain')),
                    ])
                self.assertEqual(response.status_code, 200)
                self.assertIn('text/event-stream', response.headers['content-type'])
                frames = response.text.strip().split('\n\n')
                events = [(frame.splitlines()[0][7:], json.loads(frame.splitlines()[1][6:])) for frame in frames]
                stages = [data['stage'] for name, data in events if name == 'progress']
                self.assertEqual(stages[0], 'upload')
                self.assertIn('extract', stages)
                self.assertIn('prepare', stages)
                self.assertIn('model', stages)
                self.assertEqual(stages[-1], 'verify')
                self.assertTrue(any(data.get('characters', 0) > 0 for name, data in events))
                self.assertEqual(events[-1][0], 'result')
                self.assertEqual(events[-1][1]['draft'], '测试草稿')
            with patch('backend.services.drafting.call_model', side_effect=ValueError('模型测试错误')):
                with TestClient(app) as client:
                    response = client.post('/api/draft?stream=true', files=[
                        ('application', ('a.txt', b'content', 'text/plain')),
                        ('comparison1', ('d.txt', b'prior', 'text/plain')),
                    ])
                self.assertIn('event: error', response.text)
                self.assertNotIn('event: result', response.text)
        finally:
            server.shutdown()
            server.server_close()

    def test_claim_one_reasoning_paragraphs(self):
        raw = ('1、权利要求1要求保护方法，对比文件1公开了相关特征。'
               '权利要求1与对比文件1相比，区别技术特征在于：（1）特征甲；（2）特征乙。'
               '基于上述区别技术特征，可以确定本申请所要解决的技术问题是保存数据。'
               '对于区别技术特征（1），对比文件2公开了特征甲。'
               '至于区别技术特征（2），采用该手段能够保持数据。\n\n'
               '2、权利要求2对权利要求1作了进一步的限定。附加特征（1）公开；（2）具体说理。')
        result = format_notice(raw)
        self.assertIn('相关特征。\n\n该权利要求与对比文件1相比，区别技术特征在于：\n\n（1）特征甲；\n\n（2）特征乙。\n\n基于上述', result)
        self.assertIn('保存数据。\n\n对于区别技术特征（1）', result)
        self.assertIn('特征甲。\n\n至于区别技术特征（2）', result)
        self.assertIn('附加特征（1）公开；（2）具体说理。', result)
        self.assertEqual(format_notice(result), result)

    def test_variable_file_count(self):
        with patch('backend.services.drafting.call_model', return_value='测试草稿') as model:
            with TestClient(app) as client:
                files = [('application', ('app.txt', b'application', 'text/plain'))]
                files.extend((f'comparison{i}', (f'd{i}.txt', f'document {i}'.encode(), 'text/plain')) for i in range(1, 11))
                response = client.post('/api/draft', files=files)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['documents'][-1]['label'], '对比文件10')
                self.assertIn('对比文件10', model.call_args[0][0][1]['content'])
                response = client.post('/api/draft', files=files + [('comparison11', ('x.txt', b'x', 'text/plain'))])
                self.assertEqual(response.status_code, 400)

    def test_plain_chinese_notice_format(self):
        self.assertEqual(format_notice('（参见说明书第0057—0069段）'), '（参见说明书第【0057—0069】段）')
        self.assertEqual(format_notice('（参见【说明书第[0057]段】）'), '（参见说明书第【0057】段）')
        self.assertEqual(format_notice('（参见说明书第【0057、0069】段）'), '（参见说明书第【0057、0069】段）')
        self.assertEqual(format_notice('（参见提取文本第【2】段）'), '（参见提取文本第【2】段）')
        raw = '## 审查意见\n**1、权利要求1**\n「获取图像。」[对比文件1 §2] (相当于『采集图像』), S2.1: 0.5。'
        result = format_notice(raw)
        self.assertEqual(result, '审查意见\n1、权利要求1\n获取图像（相当于采集图像）， S2.1： 0.5。')
        self.assertEqual(format_notice('“原文”；（相当于“权利要求原文”）。'), '原文（相当于权利要求原文）。')
        self.assertEqual(format_notice('```text\n正文。\n```'), '正文。')
        self.assertEqual(format_notice('公开了存储影像。，并具体公开了以下特征。'), '公开了存储影像，并具体公开了以下特征。')
        self.assertEqual(
            format_notice('依据现有申请文件，具体理由如下。\n\n1、权利要求1要求保护图像采集方法，对比文件1（公开号待核实）为最接近的现有技术。'),
            '1、权利要求1要求保护图像采集方法，对比文件1（公开号待核实）为最接近的现有技术。',
        )

    def test_fixed_file_slots(self):
        with patch('backend.services.drafting.call_model', return_value='测试草稿') as model:
            with TestClient(app) as client:
                response = client.post('/api/draft', files=[
                    ('application', ('app.txt', '权利要求1：一种装置'.encode(), 'text/plain')),
                    ('comparison1', ('first.txt', '第一份公开内容'.encode(), 'text/plain')),
                    ('comparison3', ('third.txt', '第三份公开内容'.encode(), 'text/plain')),
                ])
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual([d['label'] for d in response.json()['documents']], ['申请文件', '对比文件1', '对比文件3'])
            content = model.call_args[0][0][1]['content']
            self.assertIn('[对比文件3 §1] 第三份公开内容', content)
            self.assertNotIn('[对比文件2 §', content)

    def test_verbatim_and_budget(self):
        documents = [{'label': '申请文件', 'text': '一种装置，包括控制器'},
                     {'label': '对比文件1', 'text': '该设备设置控制器。'}]
        self.assertEqual(check_quotes('「该设备设置控制器。」相当于『包括控制器』', documents), [])
        self.assertTrue(check_quotes('「该设备自动控制。」相当于『包括控制器』', documents))
        with patch('backend.services.drafting.call_model') as model:
            with self.assertRaisesRegex(ValueError, '无法完整提交原文'):
                generate_draft([('申请文件', 'a.txt', ('长' * 60001).encode()),
                                ('对比文件1', 'd.txt', b'text')], '')
            model.assert_not_called()

    def test_adjacent_paragraph_quotes(self):
        documents = [
            {'label': '申请文件', 'text': '[申请文件 §1] 获取图像并保存。'},
            {'label': '对比文件1', 'text': '[对比文件1 §1] 相机获取影像。\n[对比文件1 §2] 影像写入存储器。\n[对比文件1 §3] 断电保留数据。'},
        ]
        self.assertEqual(check_quotes('「相机获取影像。\n影像写入存储器。」（相当于『获取图像并保存』）', documents), [])
        self.assertTrue(check_quotes('「相机获取影像。断电保留数据。」（相当于『获取图像并保存』）', documents))

    def test_upload_to_draft(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), MockModel)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with patch.dict(os.environ, {'API_BASE_URL': f'http://127.0.0.1:{server.server_port}/v1', 'MODEL': 'mock'}):
                with TestClient(app) as client:
                    response = client.post('/api/draft', files=[
                        ('application', ('application.txt', '权利要求1：一种装置'.encode(), 'text/plain')),
                        ('comparison1', ('prior.txt', '对比文件公开一种装置'.encode(), 'text/plain')),
                    ], headers={'Origin': 'http://127.0.0.1:5173'})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.headers['access-control-allow-origin'], 'http://127.0.0.1:5173')
                    self.assertIn('测试草稿', response.json()['draft'])
                    self.assertEqual([d['label'] for d in response.json()['documents']], ['申请文件', '对比文件1'])
        finally:
            server.shutdown()
            server.server_close()

    def test_status_and_invalid_upload(self):
        with TestClient(app) as client:
            self.assertNotIn('API_KEY', client.get('/api/status').text)
            self.assertEqual(client.post('/api/draft').status_code, 422)
            response = client.post('/api/draft', files=[
                ('application', ('bad.exe', b'bad', 'application/octet-stream')),
                ('comparison1', ('prior.txt', b'text', 'text/plain')),
            ])
            self.assertEqual(response.status_code, 400)
            self.assertIn('error', response.json())

if __name__ == '__main__':
    unittest.main()
