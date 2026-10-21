"""Minimal local Ollama client; asks a model for one JSON object per draft."""
import json
import urllib.request

OLLAMA = 'http://127.0.0.1:11434'
DEFAULT_MODEL = 'qwen3.8:27b-mlx'


class ModelOutputError(ValueError):
    """A completed request whose output needs a repair/retry, not a server error."""


def _cloud_name(name):
    name = name.strip().casefold()
    return ':cloud' in name or name.endswith('-cloud')


def _post(path, payload, timeout):
    request = urllib.request.Request(OLLAMA + path, json.dumps(payload).encode(),
                                     {'Content-Type': 'application/json'})
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


class OllamaClient:
    """Streams one JSON object matching ``schema`` from a local model."""

    def __init__(self, model=DEFAULT_MODEL, timeout=300, think=None, context_window=None):
        if not isinstance(model, str) or not model.strip() or len(model) > 160:
            raise ValueError('Choose a local model')
        if _cloud_name(model):
            raise ValueError('Choose a locally installed model, not a cloud model')
        self.model = model.strip()
        self.timeout = timeout
        self.think = think
        if context_window is not None and (type(context_window) is not int or context_window < 1024):
            raise ValueError('Context window must be at least 1024 tokens')
        self.context_window = context_window
        self._checked = False
        self._capabilities = None

    def _prepare(self, payload):
        if not self._checked:
            status = models()
            if not status['available']:
                raise ValueError(status['message'])
            if self.model not in status['models']:
                raise ValueError(f'Model {self.model} is not installed locally. Choose an installed model')
            self._checked = True
        if self._capabilities is None:
            self._capabilities = _post('/api/show', {'model': self.model}, 10).get('capabilities', [])
        if 'thinking' in self._capabilities:
            payload['think'] = self.think is not False
            if payload['think']:
                payload['options']['num_predict'] += 6000

    def ask(self, system, prompt, schema, seed, temperature=0.85, max_tokens=4500, on_token=None):
        """Stream the answer; ``on_token(channel, text)`` sees 'thinking'/'response' chunks."""
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
        except (OSError, ValueError) as exc:
            raise ValueError(f'Local generation failed: {exc}. Nothing was saved.') from None
        if not final.get('done'):
            raise ModelOutputError('The model stream ended before completion')
        if final.get('done_reason') == 'length':
            raise ModelOutputError('Model output was truncated; return a complete but more concise artifact')
        try:
            result = json.loads(''.join(text))
        except ValueError as exc:
            raise ModelOutputError(f'Model returned invalid JSON: {exc}') from None
        if not isinstance(result, dict):
            raise ModelOutputError('Model did not return a JSON object')
        return result
