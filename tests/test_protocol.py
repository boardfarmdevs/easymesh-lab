"""Decoder failure handling and request/response evidence semantics; no live TX."""
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from controller import frame
from protocol import build_command, decode_packet
from responder import tlv
import workbench

HOST = '02:00:00:00:00:01'
AGENT = '02:00:00:00:01:35'


class ProtocolTests(unittest.TestCase):
    def test_unknown_tlv_preserved_and_padding_not_parsed(self):
        raw = frame(AGENT, HOST, 3, 19, tlv(0xfe, b'\x01\x02\x03'))
        d = decode_packet(raw)
        self.assertEqual(d['hex'], raw.hex())
        self.assertEqual(d['tlvs'][0]['fields']['raw'], '010203')
        self.assertEqual([x['type'] for x in d['tlvs']], [0xfe, 0])
        self.assertEqual(d['tlvs'][0]['offset'], 22)

    def test_truncated_lengths_are_visible_not_silently_valid(self):
        header = frame(AGENT, HOST, 3, 1)[:22]
        d = decode_packet(header + b'\x83\x00\x10\x01')
        self.assertIn('error', d['tlvs'][0]['fields'])
        d = decode_packet(header + tlv(0x83, b'\x01'))
        self.assertIn('decode_error', d['tlvs'][0]['fields'])

    def test_raw_and_client_actions_reject_invalid_inputs(self):
        cases = [
            ('raw', {'message_type': '0x10000', 'tlvs': '[]'}),
            ('raw', {'message_type': 2, 'tlvs': '[{"type":0,"hex":""}]'}),
            ('raw', {'message_type': 2, 'tlvs': json.dumps([{'type': 254, 'hex': 'aa'*1400}])}),
            ('sta_metrics', {'station': 'not-a-mac'}),
            ('ap_metrics', {}),
        ]
        for name, params in cases:
            with self.subTest(name=name, params=str(params)[:100]):
                with self.assertRaises(ValueError):
                    build_command(name, params, {})

    def test_push_button_tlvs_decode(self):
        second = '02:00:00:00:02:3f'
        event = decode_packet(frame(HOST, '01:80:c2:00:00:13', 0x0b, 42, tlv(1, bytes.fromhex('020000000001'))+tlv(0x12, b'\x00'), 0xc0))
        self.assertEqual((event['relay'], event['tlvs'][1]['fields']['media']), (True, []))
        join = tlv(0x13, bytes.fromhex('020000000001')+b'\x00\x2a'+bytes.fromhex('020000000137')+bytes.fromhex(second.replace(':', '')))
        fields = decode_packet(frame(AGENT, HOST, 0x0c, 43, join))['tlvs'][0]['fields']
        self.assertEqual((fields['event_mid'], fields['new_interface']), (42, second))

    def test_push_button_and_agent_parameters(self):
        from protocol import LOOKUP
        [(kind, body)] = build_command('push_button', {}, {'controller': HOST})
        self.assertEqual((kind, body), (0x0b, tlv(1, bytes.fromhex('020000000001'))+tlv(0x12, b'\x00')))
        for name, params in (('push_button', {}), ('admit_agent', {}), ('admit_agent', {'agent': 'nope'}), ('topology', {'agent': 'nope'})):
            with self.subTest(name=name, params=params), self.assertRaises(ValueError):
                build_command(name, params, {})
        self.assertEqual(build_command('topology', {'agent': '02:00:00:00:02:35'}, {}), [(2, b'')])
        self.assertIn('agent', [f['name'] for f in LOOKUP['topology']['fields']])
        self.assertNotIn('agent', [f['name'] for f in LOOKUP['reonboard']['fields']])

    def test_push_button_and_admit_commands(self):
        second = '02:00:00:00:02:35'
        with tempfile.TemporaryDirectory() as tmp, patch.object(workbench, 'BASE', Path(tmp)):
            config = Path(tmp)/'config.json'; config.write_text('{}')
            sent = []
            ctl = SimpleNamespace(args=SimpleNamespace(config=config, target=AGENT), state={'controller': HOST},
                                  checkpoint=lambda: None, config={'ssid': 'Lab', 'password': 'TestSecret123', 'revision': 1},
                                  send=lambda kind, body, **kw: sent.append((kind, body, kw)) or 42)
            ctl.agents = lambda: [AGENT, *ctl.config.get('agents', [])]
            wb = workbench.Workbench(ctl)
            try:
                def run(name, params):
                    command = '%032x' % len(sent + list((Path(tmp)/'results').glob('*.json')))
                    (Path(tmp)/'commands'/f'{command}.json').write_text(json.dumps({'name': name, 'params': params}))
                    wb.tick()
                    return json.loads((Path(tmp)/'results'/f'{command}.json').read_text())
                self.assertIn('backhaul_bands', run('push_button', {})['error'])
                ctl.config['backhaul_bands'] = ['5']
                (Path(tmp)/'onboarding.paused').touch()
                self.assertIn('paused', run('push_button', {})['error'])
                (Path(tmp)/'onboarding.paused').unlink()
                self.assertEqual(run('push_button', {})['status'], 'sent')
                self.assertEqual(sent[-1][2], {'dst': '01:80:c2:00:00:13', 'flags': 0xc0})
                self.assertEqual(ctl.state['push_button']['mid'], 42)
                self.assertIn('not an admitted agent', run('topology', {'agent': second})['error'])
                ctl.state['pending_agents'] = {second: {}}
                admitted = run('admit_agent', {'agent': second.upper()}); self.assertEqual(admitted['status'], 'applied', admitted)
                self.assertEqual((json.loads(config.read_text())['agents'], ctl.state['pending_agents']), ([second], {}))
                run('topology', {'agent': second})
                self.assertEqual(sent[-1][:3], (2, b'', {'dst': second}))
            finally:
                wb.stream.close()

    def test_reply_matching_and_ack_do_not_claim_success(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(workbench, 'BASE', Path(tmp)):
            config = Path(tmp)/'config.json'; config.write_text('{}')
            ctl = SimpleNamespace(args=SimpleNamespace(config=config, target=AGENT), state={}, checkpoint=lambda: None)
            wb = workbench.Workbench(ctl)
            try:
                command = 'a'*32
                wb.result(command, name='steer', status='processing')
                wb.command_id = command
                wb.packet('TX', frame(HOST, AGENT, 0x8014, 77))
                wb.command_id = None
                result = lambda: json.loads((Path(tmp)/'results'/f'{command}.json').read_text())
                wb.packet('RX', frame(AGENT, HOST, 0x8000, 78))  # wrong MID
                wb.packet('RX', frame('02:00:00:00:00:01', HOST, 0x8000, 77))  # wrong peer
                self.assertEqual(result()['status'], 'sent')
                wb.packet('RX', frame(AGENT, HOST, 0x8000, 77))
                self.assertEqual(result()['status'], 'acknowledged')
                self.assertIn(77, wb.pending)  # ACK does not finish the experiment.
                wb.packet('RX', frame(AGENT, HOST, 0x8015, 77))
                self.assertEqual(result()['status'], 'response_received')
                self.assertIn('Receipt only', result()['note'])
                self.assertNotIn(77, wb.pending)
                # Expiry reports lack of evidence, never unsupported or success.
                wb.result(command, status='sent')
                wb.pending[88] = {'id': command, 'expected': [3], 'time': time.time()-31}
                wb.tick()
                self.assertEqual(result()['status'], 'no_response')
                self.assertIn('does not prove', result()['note'])
            finally:
                wb.stream.close()


if __name__ == '__main__':
    unittest.main()
