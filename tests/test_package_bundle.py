import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

from package_bundle import LIBRARY, driver_meta, emu_files, min_api, write_zip
from release_version import EMU_PREFIX, PREFIX

MESA = 'a' * 40
ADRENOTOOLS_KEYS = ['schemaVersion', 'name', 'description', 'author', 'packageVersion', 'vendor', 'driverVersion',
                    'minApi', 'libraryName']
DROIDDECK_BUNDLE = re.compile(r'^DD-Turnip-v\d+\.\d+\.\d+\.zip$')


def versions(*names, file='libc.so'):
    lines = ["Version needs section '.gnu.version_r' contains 1 entry:", f'  000000: Version: 1  File: {file}  Cnt: {len(names)}']
    lines += [f'  0x{i:04x}:   Name: {name}  Flags: none  Version: {i + 2}' for i, name in enumerate(names)]
    return '\n'.join(lines)


class MinApiTest(unittest.TestCase):
    def test_c11_threads_need_android_11(self):
        self.assertEqual(min_api(versions('LIBC', 'LIBC_N', 'LIBC_P', 'LIBC_R')), 30)

    def test_older_symbols_keep_the_floor(self):
        self.assertEqual(min_api(versions('LIBC', 'LIBC_N')), 29)

    def test_newer_symbols_raise_it(self):
        self.assertEqual(min_api(versions('LIBC', 'LIBC_U')), 34)

    def test_glibc_versions_fail(self):
        with self.assertRaises(SystemExit):
            min_api(versions('GLIBC_2.17', file='libc.so.6'))

    def test_unknown_bionic_versions_fail(self):
        with self.assertRaises(SystemExit):
            min_api(versions('LIBC', 'LIBC_Z'))


class EmuPackageTest(unittest.TestCase):
    def files(self):
        return emu_files('1.2.3', '26.3.0-devel', MESA, b'ELF', 30, {'LICENSES/GPL-3.0.txt': b'GPL'})

    def test_layout_loads_as_an_adrenotools_package(self):
        files = self.files()
        self.assertEqual(sorted(files), sorted(['meta.json', LIBRARY, 'NOTICE', 'LICENSES/GPL-3.0.txt']))
        self.assertEqual(files[LIBRARY], b'ELF')

    def test_meta_has_the_fields_emulator_loaders_read(self):
        meta = json.loads(self.files()['meta.json'])
        self.assertEqual(list(meta), ADRENOTOOLS_KEYS)
        self.assertEqual(meta['schemaVersion'], 1)
        self.assertEqual(meta['name'], 'DD-Turnip-Emu v1.2.3')
        self.assertEqual(meta['vendor'], 'Mesa')
        self.assertEqual(meta['packageVersion'], '1')
        self.assertRegex(meta['driverVersion'], r'^[0-9]+.[0-9]+.[0-9]+(-.+)?$')
        self.assertEqual(meta['minApi'], 30)
        self.assertIsInstance(meta['minApi'], int)
        self.assertEqual(meta['libraryName'], LIBRARY)
        self.assertIn('26.3.0-devel', meta['description'])

    def test_notice_points_at_the_shared_source_on_this_repository(self):
        text = self.files()['NOTICE'].decode()
        self.assertTrue(text.startswith('DD-Turnip-Emu-v1.2.3\n'))
        self.assertIn('DD-Turnip-v1.2.3-source.tar.xz', text)
        self.assertIn('https://github.com/Droid-Deck/Drivers/releases/tag/DD-Turnip-v1.2.3', text)
        self.assertNotIn('Drivers-CI', text)

    def test_android_bundle_meta_shares_the_schema(self):
        meta = driver_meta('android', '1.2.3', '26.3.0-devel', MESA, 'd', 30)
        self.assertEqual(list(meta), ADRENOTOOLS_KEYS)
        self.assertEqual(meta['driverVersion'], 'DD-Turnip-v1.2.3')
        self.assertEqual(meta['minApi'], 30)

    def test_zip_and_checksum(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / f'{EMU_PREFIX}1.2.3.zip'
            digest = write_zip(path, self.files())
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(json.loads(archive.read('meta.json'))['libraryName'], LIBRARY)
            self.assertEqual((Path(work) / f'{EMU_PREFIX}1.2.3.zip.sha256').read_text(),
                             f'{digest}  {EMU_PREFIX}1.2.3.zip\n')


class AssetNameTest(unittest.TestCase):
    def test_same_version_as_the_bundle(self):
        self.assertEqual(f'{EMU_PREFIX}0.9.1.zip', 'DD-Turnip-Emu-v0.9.1.zip')
        self.assertEqual(f'{PREFIX}0.9.1.zip', 'DD-Turnip-v0.9.1.zip')

    def test_droiddeck_bundle_match_skips_the_emulator_package(self):
        self.assertTrue(DROIDDECK_BUNDLE.match(f'{PREFIX}0.9.1.zip'))
        self.assertFalse(DROIDDECK_BUNDLE.match(f'{EMU_PREFIX}0.9.1.zip'))
        self.assertFalse(DROIDDECK_BUNDLE.match(f'{EMU_PREFIX}0.9.1.zip.sha256'))


if __name__ == '__main__':
    unittest.main()
