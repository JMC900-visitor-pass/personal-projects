"""Concise previews and complete, playable Markdown cards."""


def stat_line(card):
    stats = ' · '.join(f'{key.upper()} {value}' for key, value in card['stats'].items())
    return f'Level {card["level"]} · {stats} · TN {card["tn"]} · {card["attack"]["damage_die"]}'


def card_to_markdown(card):
    attack = card['attack']
    bonus = f' + ATK ({attack["damage_bonus"]})' if card['rules']['atk_role'] == 'damage' else ''
    lines = [f'## {card["name"]}', '', card['blurb'], '', stat_line(card), '',
             f'**{attack["name"]}** · range {attack["range"]} · {"melee" if card["melee"] else "ranged"}',
             f'Hit: {attack["test"]}.',
             f'On hit: {attack["damage_die"]}{bonus} − target DEF (minimum 0).']
    if card['move']:
        move = card['move']
        lines += ['', f'**{move["name"]}** · custom move ({move["cost"]} design points)',
                  f'Trigger: {move["trigger"]}', f'Effect: {move["effect"]}', f'Limit: {move["limit"]}']
    lines += ['', f'**Tactics:** {card["tactics"]}', f'**Counterplay:** {card["weakness"]}']
    budget = card['budget']
    lines += ['', f'Design budget: {budget["stats"]} stats + {budget["move"]} move / {budget["limit"]} available.',
              'Custom move text is a playtest draft; stat and budget checks do not validate its balance.']
    return '\n'.join(lines)


def render_document(cards, title='Monster Roster'):
    lines = [f'# {title}', '']
    seen = set()
    for card in cards:
        if card['rules_summary'] not in seen:
            lines += [card['rules_summary'], '']
            seen.add(card['rules_summary'])
    lines += [card_to_markdown(card) + '\n' for card in cards]
    return '\n'.join(lines).rstrip() + '\n'
