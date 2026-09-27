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
