"""Minimal local Ollama client used by the skirmish generation agent."""
import json
import urllib.request

OLLAMA = 'http://127.0.0.1:11434'
DEFAULT_MODEL = 'qwen3.5:0.8b'


def _cloud_name(name):
    name = name.strip().casefold()
    return ':cloud' in name or name.endswith('-cloud')


def _post(path, payload, timeout):
    request = urllib.request.Request(OLLAMA + path, json.dumps(payload).encode(), {'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def models():
    """Locally installed models only; cloud-proxied models are hidden."""
    try:
        with urllib.request.urlopen(OLLAMA + '/api/tags', timeout=3) as response:
            names = [entry['name'] for entry in json.load(response).get('models', [])
                     if not _cloud_name(entry['name']) and not entry.get('remote_host')]
        return {'available': True, 'models': names, 'message': 'Local Ollama connected'}
    except (OSError, ValueError, KeyError) as exc:
        return {'available': False, 'models': [], 'message': f'Ollama unavailable: {exc}'}


class OllamaWriter:
    """Asks a local model for one JSON object that matches ``schema``."""

    def __init__(self, model=DEFAULT_MODEL, timeout=240, think=False, context_window=None):
        if not isinstance(model, str) or not model.strip() or len(model) > 160:
            raise ValueError('Choose a local model')
        if _cloud_name(model):
            raise ValueError('Choose a locally installed model, not a cloud model')
        self.model = model.strip()
        self.timeout = timeout
        self.think = bool(think)
        if context_window is not None and (type(context_window) is not int or context_window < 1024):
            raise ValueError('Context window must be at least 1024 tokens')
        self.context_window = context_window
        self._checked = False

    def _prepare(self, payload):
        if not self._checked:
            status = models()
            if not status['available']:
                raise ValueError(status['message'])
            if self.model not in status['models']:
                raise ValueError(f'Model {self.model} is not installed locally. Choose an installed model')
            self._checked = True
        # Thinking models spend the token budget reasoning unless told not to.
        if 'thinking' in _post('/api/show', {'model': self.model}, 10).get('capabilities', []):
            payload['think'] = self.think
            if self.think:
                payload['options']['num_predict'] += 6000

    def ask(self, system, prompt, schema, seed, temperature=0.9, max_tokens=900, on_token=None):
        """Stream the answer; ``on_token(channel, text)`` sees 'thinking' and 'response' chunks as they arrive."""
        payload = {'model': self.model, 'stream': True, 'format': schema, 'system': system,
                   'prompt': json.dumps(prompt, ensure_ascii=False),
                   'options': {'temperature': temperature, 'seed': seed, 'num_predict': max_tokens}}
        if self.context_window is not None:
            payload['options']['num_ctx'] = self.context_window
        try:
            self._prepare(payload)
            request = urllib.request.Request(OLLAMA + '/api/generate', json.dumps(payload).encode(),
                                             {'Content-Type': 'application/json'})
            text, final = [], {}
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                for line in response:
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if chunk.get('error'):
                        raise ValueError(chunk['error'])
                    for channel in ('thinking', 'response'):
                        if chunk.get(channel) and on_token:
                            on_token(channel, chunk[channel])
                    text.append(chunk.get('response', ''))
                    if chunk.get('done'):
                        final = chunk
            if final.get('done_reason') == 'length':
                raise ValueError('model output was truncated')
            result = json.loads(''.join(text))
        except (OSError, ValueError) as exc:
            raise ValueError(f'Local generation failed: {exc}. Nothing was saved.') from None
        if not isinstance(result, dict):
            raise ValueError('Local generation failed: model did not return a JSON object')
        return result
