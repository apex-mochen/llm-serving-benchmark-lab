from pathlib import Path
import unittest
from unittest.mock import Mock
from experiment_schedule import validate_wakeup

class Tests(unittest.TestCase):
    def test_on_time_no_added_io(self):
        writer=Mock(); validate_wakeup(Path('/fixture'),8,0,.01,writer,[]);writer.assert_not_called()
    def test_late_value_saved(self):
        writer=Mock()
        with self.assertRaisesRegex(RuntimeError,'lateness >50ms'): validate_wakeup(Path('/fixture'),8,0,.08,writer,[])
        self.assertEqual(writer.call_args.args[1]['lateness_ms'],80)
    def test_write_failure_does_not_mask_gate(self):
        errors=[]
        with self.assertRaisesRegex(RuntimeError,'lateness >50ms'): validate_wakeup(Path('/fixture'),8,0,.08,Mock(side_effect=OSError('fixture')),errors)
        self.assertEqual(errors[0]['phase'],'schedule_abort_write')

if __name__=='__main__': unittest.main(verbosity=2)
