"""Explore three designs, develop one, then refine the current card in place."""
import json
import sys

from . import markdown, roles
from .level import DEFAULT_RULES, character
from .ollama import ModelOutputError


class Studio:
    def __init__(self, client, seed, progress=None, level=1, rules=DEFAULT_RULES):
        character(level, rules)
        self.client, self.seed, self.level, self.rules = client, seed, level, rules
        self.progress = progress or (lambda text: print(text, file=sys.stderr, flush=True))
        self.calls = 0
        self.previous = []
        self.feedback = []

    def _request(self, prompt, schema, parse, max_tokens):
        """Repair malformed, over-budget, or duplicated designs with concrete feedback."""
        request = dict(prompt)
        for attempt in range(3):
            self.calls += 1
            result = None
            try:
                result = self.client.ask(roles.SYSTEM, request, schema, self.seed + self.calls,
                                         temperature=0.85 if attempt == 0 else 0.55,
                                         max_tokens=max_tokens + 1000 * attempt)
            except ModelOutputError as exc:
                error = str(exc)
            else:
                try:
                    return parse(result)
                except (ValueError, KeyError, TypeError) as exc:
                    error = str(exc)
            self.progress(f'Design check: {error}')
            if attempt < 2:
                self.progress('Asking the model to repair the design...')
                request = {**prompt, 'repair': {'error': error,
                           'previous_response': json.dumps(result, ensure_ascii=False)[:18000],
                           'instruction': 'Return the complete corrected artifact, not a patch. Preserve valid work.'}}
        raise RuntimeError(f'The model could not produce a valid design after 3 attempts: {error}')

    def generate_variations(self, role, concept, theme):
        template = roles.template(role, self.level, self.rules)
        prompt = roles.design_prompt(template, concept, theme, self.previous)
        prompt['task'] = (
            'Explore exactly three different creatures within this brief at the SAME level. '
            'Each must have a different stat allocation, identity, monster name and attack name. '
            'Choose different strengths, weaknesses, ranges or moves. Do not merely rename '
            'one design. Give each a playable first draft; the chosen one will receive a development pass.')

        def parse(result):
            if not isinstance(result, dict) or set(result) != {'monsters'} or not isinstance(result['monsters'], list):
                raise ValueError('Return an object containing a monsters array')
            cards = [roles.clean_card(raw, role, template) for raw in result['monsters']]
            roles.validate_variations(cards, self.previous)
            return cards

        cards = self._request(prompt, roles.roster_schema(template), parse, max_tokens=4500)
        self.previous.extend(roles.summary(card) for card in cards)
        self.previous = self.previous[-12:]
        return cards

    def _revise(self, role, concept, chosen, task, theme='', preserve_name=False):
        template = roles.template(role, self.level, self.rules)
        prompt = roles.design_prompt(template, concept, theme, self.previous)
        prompt.update(task=task, chosen_card=roles.design_data(chosen), feedback_history=self.feedback[-6:])

        def parse(raw):
            card = roles.clean_card(raw, role, template)
            if preserve_name and card['name'] != chosen['name']:
                raise ValueError('Keep the selected monster name during development')
            return card

        return self._request(prompt, roles.card_schema(template), parse, max_tokens=2200)

    def develop(self, role, concept, chosen, theme=''):
        self.progress(f'Developing {chosen["name"]}: move clarity, counterplay and names...')
        return self._revise(role, concept, chosen,
            'Develop this selected design into its finished playable draft. Preserve its monster name '
            'and distinctive identity. Check stat trade-offs, action cost, trigger, targets, duration, '
            'limits and practical counterplay. Resolve vague move wording. Improve attack/move names '
            'after their effects are clear; prefer specific, evocative language. Preserve good choices '
            'instead of changing everything. Return the full card.', theme, preserve_name=True)

    def refine(self, role, concept, chosen, feedback, theme=''):
        history = self.feedback + [feedback]
        original = self.feedback
        self.feedback = history
        try:
            return self._revise(role, concept, chosen,
                'Apply the latest feedback to this card. Change stats, range, move, tactics or names '
                'when requested; otherwise preserve the current design and earlier accepted feedback. '
                f'Latest feedback: {feedback}', theme)
        except Exception:
            self.feedback = original
            raise

    def display(self, cards):
        for index, card in enumerate(cards, 1):
            print(f'\n{index}. {card["name"]} — {card["identity"]}')
            print(markdown.stat_line(card))
            print(f'   Attack: {card["attack"]["name"]} · range {card["attack"]["range"]}')
            if card['move']:
                print(f'   Move: {card["move"]["name"]} — {card["move"]["effect"]}')
            print(f'   Counterplay: {card["weakness"]}')

    def choose(self, count):
        while True:
            choice = input(f'\nDevelop which design? [1–{count}]: ').strip()
            if choice.isdigit() and 1 <= int(choice) <= count:
                return int(choice) - 1
            print('Enter a number from the list.')

    def session(self, role, concept, theme):
        self.feedback = []
        self.progress(f'Exploring 3 distinct Level {self.level} {role} designs...')
        cards = self.generate_variations(role, concept, theme)
        developed, histories = set(), {}
        while True:
            self.display(cards)
            index = self.choose(len(cards))
            self.feedback = list(histories.get(index, []))
            if index not in developed:
                cards[index] = self.develop(role, concept, cards[index], theme)
                developed.add(index)
            while True:
                chosen = cards[index]
                print('\n' + markdown.card_to_markdown(chosen))
                choice = input('\nEnter = keep · r = refine · b = other designs · n = new designs: ').strip().lower()
                if choice in ('', '1', 'keep'):
                    return chosen
                if choice in ('r', '2', 'refine'):
                    feedback = input('What should change? ').strip()
                    if feedback:
                        self.progress('Refining the current card...')
                        try:
                            cards[index] = self.refine(role, concept, chosen, feedback, theme)
                        except (ValueError, OSError, RuntimeError) as exc:
                            self.progress(f'Refinement failed; keeping the current card. {exc}')
                        else:
                            histories[index] = list(self.feedback)
                    continue
                if choice in ('b', 'back'):
                    break
                if choice in ('n', '3', 'new', 'restart'):
                    self.progress('Exploring new designs...')
                    cards = self.generate_variations(role, concept, theme)
                    developed, histories = set(), {}
                    break
                print('Choose keep, refine, other designs, or new designs.')

    def build(self, role, concept, theme='', count=1):
        if type(count) is not int or count < 1:
            raise ValueError('Card count must be at least 1')
        cards = []
        for number in range(count):
            print(f'\n=== {role.capitalize()} {number + 1}/{count} · Level {self.level} ===')
            card = self.session(role, concept, theme)
            cards.append(card)
            self.previous.append(roles.summary(card))
            self.previous = self.previous[-12:]
        return cards
