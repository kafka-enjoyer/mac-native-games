"""Work-folder isolation, including source/cache directory symlinks."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import build_app
import hashlib


class WorkDirectoryTests(unittest.TestCase):
    def fixture(self, root):
        source = root/'source'
        source.mkdir()
        (source/'requirements.txt').write_text('')
        translator = root/'translator/totk_xlate'
        translator.parent.mkdir()
        translator.write_bytes(b'source-built translator')
        translator.chmod(0o755)
        translator.with_suffix('.sha256').write_text(hashlib.sha256(translator.read_bytes()).hexdigest())
        source_patch = mock.patch.object(build_app, 'SOURCE_TRANSLATOR', translator)
        source_patch.start()
        self.addCleanup(source_patch.stop)
        external = root/'shared-tooling'
        (external/'spirv-cross').mkdir(parents=True)
        (external/'spirv-cross/keep.txt').write_text('shared dependency must survive')
        return source, external, root/'work'

    def test_existing_tooling_link_is_detached_before_child_links_change(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source, external, work=self.fixture(root)
            (work/'totk').mkdir(parents=True)
            (work/'totk/tooling').symlink_to(external,target_is_directory=True)
            with mock.patch.object(build_app,'GAME',source), \
                 mock.patch.object(build_app,'run'), \
                 mock.patch.object(build_app,'local_source'), \
                 mock.patch.object(build_app,'local_python_dependencies',return_value=(root/'lock',root/'wheels')):
                tree=build_app.prepare_work(work,Path('/usr/bin/python3'),work/'logs')
            self.assertFalse((tree/'tooling').is_symlink())
            self.assertTrue((tree/'tooling/spirv-cross').is_symlink())
            self.assertEqual((external/'spirv-cross/keep.txt').read_text(),'shared dependency must survive')

    @unittest.skipUnless(shutil.which('rsync'),'rsync needed for real source-copy check')
    def test_source_cache_symlinks_are_excluded_by_the_real_copier(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source, external, work=self.fixture(root)
            (source/'tooling').symlink_to(external,target_is_directory=True)
            (source/'extracted').symlink_to(external,target_is_directory=True)
            def run(command,*_args,**_kwargs):
                if str(command[0])=='rsync':
                    subprocess.run([str(x) for x in command],check=True,capture_output=True)
            with mock.patch.object(build_app,'GAME',source), \
                 mock.patch.object(build_app,'run',side_effect=run), \
                 mock.patch.object(build_app,'local_source'), \
                 mock.patch.object(build_app,'local_python_dependencies',return_value=(root/'lock',root/'wheels')):
                tree=build_app.prepare_work(work,Path('/usr/bin/python3'),work/'logs')
            self.assertFalse((tree/'extracted').exists())
            self.assertFalse((tree/'extracted').is_symlink())
            self.assertFalse((tree/'tooling').is_symlink())
            self.assertEqual((external/'spirv-cross/keep.txt').read_text(),'shared dependency must survive')

    def test_local_source_can_replace_a_dangling_cache_link(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            missing=root/'external-missing'
            cache=root/'cache'
            cache.symlink_to(missing,target_is_directory=True)
            source=root/'dependencies/sources/example'
            source.mkdir(parents=True)
            (source/'source.c').write_bytes(b'local source')
            manifest={'sources':{'example':{'files':{'source.c':hashlib.sha256(b'local source').hexdigest()}}}}
            with mock.patch.object(build_app,'DEPENDENCIES',root/'dependencies'), \
                 mock.patch.object(build_app,'offline_manifest',return_value=manifest), \
                 mock.patch.object(build_app,'run') as run:
                build_app.local_source('example',cache,root/'copy.log')
            self.assertTrue(cache.is_dir())
            self.assertFalse(cache.is_symlink())
            self.assertFalse(missing.exists())
            self.assertEqual(run.call_count,1)
            self.assertEqual(run.call_args.args[0][0],'rsync')


if __name__=='__main__':
    unittest.main()
