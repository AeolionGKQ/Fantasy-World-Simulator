import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR.parent))
from api.content_registry import ContentRegistry


class GMWritingContextTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.api = self.workspace / 'apps' / 'api'
        self.api.mkdir(parents=True)
        original = ContentRegistry(API_DIR)
        # These source snapshots stand in for an existing save's frozen revision.
        self.documents = list(original.documents)
        self.manifest = original.manifest
        for doc in self.documents:
            target = (self.api / doc['source_path'] if doc['source_path'].startswith('content/')
                      else self.workspace / doc['source_path'])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(doc['raw_bytes'])
        self.guide = '# Writing guidance fixture\nA new style for existing saves.\n'
        (self.workspace / 'GM写作规范.md').write_text(self.guide, encoding='utf-8')
        self.registry = ContentRegistry(self.api)
        self.state = {'state_version': 0, 'location': {'id': 'selavia_port'},
                      'regional_quests': {}, 'narration': {}}

    def build(self, kind):
        return self.registry.build_messages(
            self.state, {'action_type': 'turn'}, [], [], [], [], {},
            self.documents, kind, self.manifest)

    def test_current_writing_context_reaches_gm_system_with_frozen_save_documents(self):
        messages, manifest = self.build('gm_turn')
        self.assertEqual('system', messages[0]['role'])
        self.assertEqual(1, messages[0]['content'].count(self.guide))
        self.assertNotIn(self.guide, messages[1]['content'])
        self.assertIn('gm-turn/2', messages[0]['content'])
        self.assertEqual('GM写作规范.md', manifest['gm_writing_guidelines']['source_path'])
        self.assertEqual(hashlib.sha256(self.guide.encode()).hexdigest(),
                         manifest['gm_writing_guidelines']['raw_sha256'])

    def test_story_arc_archival_does_not_receive_turn_writing_context(self):
        messages, manifest = self.build('story_arc')
        self.assertNotIn(self.guide, messages[0]['content'])
        self.assertNotIn('gm_writing_guidelines', manifest)
        self.assertIn('story-arc/1', messages[0]['content'])

    def test_image_prompt_does_not_receive_turn_writing_context(self):
        frozen = {'documents': self.documents, 'state': self.state, 'turn': {},
                  'early_summaries': [], 'recent_full_turns': [], 'memories': [], 'arcs': []}
        messages = self.registry.build_image_prompt_messages(frozen, '1024x1024')
        self.assertNotIn(self.guide, messages[0]['content'])
        self.assertEqual('system', messages[0]['role'])


if __name__ == '__main__':
    unittest.main()
