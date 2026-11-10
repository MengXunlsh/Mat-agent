"""Check the generated research preset against the pinned Harness configuration."""
import tempfile
import unittest
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_harness_web import ROOT, prepare


class ResearchPresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.home.cleanup)
        cls.foundation = ROOT / 'integrations/deepseek-harness/foundation'
        native_file = ROOT / 'integrations/deepseek-harness/web-runtime/node_modules/@deepseek-ai/dsh-web-app/presets/standard.patch.yml'
        native = yaml.load(native_file.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
        generated = yaml.load(prepare(Path(cls.home.name)).read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
        cls.native = native[0]['insert'][0]['config']['plugins']
        cls.research = generated[-1]['insert'][0]['config']['plugins']

    def test_research_prompts_reach_generated_preset(self):
        plugins = {item['id']: item for item in self.research}
        self.assertEqual(plugins['persona']['config']['prefix'], (self.foundation / 'research-persona.txt').read_text(encoding='utf-8').strip())
        planning = plugins['planning']['config'][0]
        self.assertEqual(planning['config']['section'], (self.foundation / 'research-plan.txt').read_text(encoding='utf-8').strip())
        self.assertEqual(planning['name'], '@deepseek-ai/dsh-plan-mode')

    def test_default_model_survives_regenerating_the_launch_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            prepare(home)
            settings = home / 'profiles/web/cordis.patch.yml'
            settings.write_text('- id: agent-default-model\n  config:\n    provider: local-provider\n    model: research-model\n    reasoningEffort: high\n')
            for _ in range(2):
                overlay = yaml.load(prepare(home).read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
                self.assertFalse(any(row.get('id') == 'agent-default-model' for row in overlay))
                rows = yaml.load(settings.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
                selected = next(row['config'] for row in rows if row.get('id') == 'agent-default-model')
                self.assertEqual(selected, dict(provider='local-provider', model='research-model', reasoningEffort='high'))

    def test_native_tools_and_control_mechanisms_are_preserved(self):
        generated = {item['id']: item for item in self.research}
        for original in self.native:
            with self.subTest(plugin=original['id']):
                actual = generated[original['id']]
                if original['id'] == 'persona':
                    self.assertEqual(actual['name'], original['name'])
                elif original['id'] == 'planning':
                    expected = {**original, 'config': actual['config']}
                    self.assertEqual(actual, expected)
                    self.assertEqual(len(actual['config']), len(original['config']))
                    self.assertEqual(actual['config'][0]['id'], original['config'][0]['id'])
                elif original['id'] == 'tool-schedule':
                    self.assertEqual(actual, {**original, 'disabled': 'true'})
                elif original['id'] == 'skill-filesystem':
                    self.assertEqual(actual, {**original, 'config': {'bundledSkillDir': (self.foundation / 'skills').as_posix(), 'includeDefaultRoots': 'false'}})
                else:
                    self.assertEqual(actual, original)


if __name__ == '__main__':
    unittest.main()
