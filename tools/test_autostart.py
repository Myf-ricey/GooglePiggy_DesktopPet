"""Startup registration must be confirmed independently before success."""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pig_pet as pet
import windows_autostart as backend


class AutostartTests(unittest.TestCase):
    def test_packaged_command_matches_installer_quoting(self):
        exe=str(Path('C:/GooglePiggy/pig_pet.exe').resolve())
        with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable',exe):
            self.assertEqual(pet.startup_command(Path('C:/GooglePiggy')),'"'+exe+'"')

    def test_saved_enabled_does_not_skip_system_reconciliation(self):
        with patch.object(pet,'_legacy_autostart_preference',return_value=1),patch.object(backend,'request',return_value={'enabled':True}) as check,patch.object(pet,'write_json_atomic'):
            pet.configure_first_autostart(Path.cwd(),previous_install=True)
        self.assertEqual(check.call_args.args[0],'reconcile')
        self.assertEqual(check.call_args.kwargs['legacy_preference'],1)

    def test_invalid_run_command_is_not_enabled(self):
        with patch.object(pet,'autostart_request',return_value={'enabled':False,'registered':True,'command_matches':False}):
            self.assertFalse(pet.is_autostart_enabled())

    def test_enable_failure_is_not_success(self):
        with patch.object(pet,'autostart_request',return_value={'enabled':False,'registered':False}):
            with self.assertRaises(OSError):pet.set_autostart(True,Path.cwd())

    def test_disable_requires_removing_command(self):
        with patch.object(pet,'autostart_request',return_value={'enabled':False,'registered':True}):
            with self.assertRaises(OSError):pet.set_autostart(False,Path.cwd())

    def test_menu_write_failure_is_reported_without_quitting(self):
        with patch.object(pet,'is_autostart_enabled',return_value=False),patch.object(pet,'set_autostart',side_effect=OSError('access denied')),patch.object(pet.user32,'MessageBoxW') as message:
            pet.toggle_autostart_from_menu(Path.cwd(),None)
        self.assertIn('access denied',message.call_args.args[1])

    def test_provider_error_and_timeout_are_not_false_disabled(self):
        with patch.object(backend.subprocess,'run',return_value=subprocess.CompletedProcess([],1,b'',b'Windows error 5')):
            with self.assertRaises(OSError):backend.request('inspect','x','x')
        with patch.object(backend.subprocess,'run',side_effect=subprocess.TimeoutExpired('powershell',20)):
            with self.assertRaises(OSError):backend.request('inspect','x','x')

    def test_invalid_provider_response_is_rejected(self):
        for response in (b'{}',b'null',b'not JSON'):
            with patch.object(backend.subprocess,'run',return_value=subprocess.CompletedProcess([],0,response,b'')):
                with self.assertRaises(OSError):backend.request('inspect','x','x')


if __name__=='__main__':unittest.main(verbosity=2)
