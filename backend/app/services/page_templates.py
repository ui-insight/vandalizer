"""Design-only Page templates and evidence-checked, deterministic filling.

The original HTML/text never enters template storage. Only a conservative
layout vocabulary and neutral fields survive conversion. New values must be
quoted from the newly authorized file; the model cannot submit replacement HTML.
"""
from copy import deepcopy
import hashlib
import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup, NavigableString
from fastapi import HTTPException
from pymongo import ReturnDocument

from app.services import artifacts

MISSING = 'Not in this file'
# These are design labels, never arbitrary text copied from a source Page.
LABELS = {s.casefold(): s for s in (
    'Overview', 'Budget', 'Budget dashboard', 'Budget summary', 'Award summary', 'Award details',
    'Summary', 'Contents', 'Table of contents', 'Source notes', 'Calculated summary', 'Guidance',
    'Category', 'Description', 'Amount', 'Total', 'Subtotal', 'Year', 'Period', 'Start date', 'End date',
    'Personnel', 'Equipment', 'Travel', 'Supplies', 'Other', 'Direct costs', 'Indirect costs',
    'Fringe benefits', 'Tuition', 'Subawards', 'Cost share', 'Sponsor', 'Principal investigator',
    'Award number', 'Project title', 'Contact', 'Notes', 'Sources', 'Budget by category',
    'Budget by year', 'Reporting', 'Deadlines', 'Next steps', 'Back to top',
)}
COLORS = 'transparent currentcolor black white navy teal blue green red gray grey orange purple yellow silver'.split()
KEYWORDS = set(('none auto inherit initial normal bold bolder lighter italic underline solid dashed dotted hidden visible '
                'block inline inline-block flex inline-flex grid table table-row table-cell collapse separate '
                'relative static sticky left right center justify start end space-between space-around '
                'wrap nowrap row column border-box content-box serif sans-serif monospace system-ui '
                'arial inter georgia helvetica verdana tahoma uppercase lowercase capitalize baseline stretch repeat minmax min-content max-content '
                'thin medium thick clip scroll all ease ease-in-out linear').split() + COLORS)
PROPERTIES = set(('color background background-color border-color border-top-color border-bottom-color border-left-color border-right-color '
                  'display position top bottom left right gap row-gap column-gap padding padding-top padding-bottom padding-left padding-right '
                  'margin margin-top margin-bottom margin-left margin-right width max-width min-width height min-height max-height '
                  'font font-size font-weight font-style font-family line-height letter-spacing text-align text-decoration text-transform '
                  'border border-top border-bottom border-left border-right border-width border-style border-radius border-collapse '
                  'box-sizing box-shadow overflow overflow-x overflow-y vertical-align grid-template-columns flex flex-direction '
                  'flex-wrap align-items justify-content list-style-type opacity outline outline-offset scroll-margin-top').split())


def _css_value(value):
    # No strings, URLs, escapes, custom properties, data attributes, or generated content.
    if not re.fullmatch(r'[\w\s#.,()%+/-]+', value, re.ASCII):
        return False
    scrubbed = re.sub(r'#[a-fA-F0-9]{3,8}\b|[-+]?\d*\.?\d+(?:px|rem|em|vh|vw|ch|%|fr|deg)?', '', value)
    return all(word.lower() in KEYWORDS | {'rgb', 'rgba', 'hsl', 'hsla', 'calc'} for word in re.findall(r'[a-zA-Z_][\w-]*', scrubbed))


def _declarations(text, *, bar=False):
    result = []
    for item in text.split(';'):
        prop, _, value = item.partition(':')
        prop, value = prop.strip().lower(), value.strip()
        # All non-full percentage dimensions may encode data. Rebuild them from new values.
        if prop in {'width', 'height'} and re.fullmatch(r'\d+(?:\.\d+)?%', value) and value != '100%':
            value = '0%'
        if bar and prop in {'width', 'height'}:
            value = '0%'
        if prop in PROPERTIES and _css_value(value):
            result.append(f'{prop}:{value}')
    return ';'.join(result)


def design(html):
    cleaned, _ = artifacts.clean_html(html, 'Template')
    soup = BeautifulSoup(cleaned, 'html.parser')
    for node in soup.select('img, title'):
        # Raster charts and contact metadata can encode source data.
        node.decompose()
    classes, ids = {}, {}
    for tag in soup.find_all(True):
        for cls in tag.get('class', []):
            classes.setdefault(cls, f'tc{len(classes)+1}')
        if tag.get('id'):
            ids.setdefault(tag['id'], f'ts{len(ids)+1}')
    def stylesheet(css):
        rules = []
        css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
        offset = 0
        while offset < len(css):
            begin = css.find('{', offset)
            if begin < 0:
                break
            selector = css[offset:begin].strip()
            depth, end = 1, begin + 1
            while end < len(css) and depth:
                depth += (css[end] == '{') - (css[end] == '}')
                end += 1
            if depth:
                break
            declarations = css[begin + 1:end - 1]
            offset = end
            if selector.startswith('@'):
                if re.fullmatch(r'@media\s+(?:screen\s+and\s+)?\(\s*(?:min|max)-width\s*:\s*\d+(?:\.\d+)?(?:px|em|rem)\s*\)', selector):
                    rules.append(selector + '{' + stylesheet(declarations) + '}')
                continue
            if not re.fullmatch(r'[\w\s.#,:*>+~-]+', selector, re.ASCII):
                continue
            is_chart = bool(re.search(r'bar|progress|fill', selector, re.I))
            selector = re.sub(r'([.#])([\w-]+)', lambda m: m[1] + (classes if m[1] == '.' else ids).get(m[2], 'unused'), selector)
            words = re.findall(r'(?<![.#\w-])([a-zA-Z][\w-]*)', selector)
            if any(word not in artifacts.ALLOWED_TAGS | {'hover', 'focus', 'focus-visible', 'first-child', 'last-child', 'root'} for word in words):
                continue
            value = _declarations(declarations, bar=is_chart)
            if value:
                rules.append(f'{selector}{{{value}}}')
        return '\n'.join(rules)

    for style in soup.find_all('style'):
        style.string = stylesheet(style.get_text())
    # Preserve a guidance box's position and theme, but never its old factual text.
    guidance_box = next((tag for tag in soup.body.find_all(True) if
        re.search(r'guidance', ' '.join(tag.get('class', [])), re.I) or
        (tag.name == 'aside' and tag.find(['h2', 'h3']) and tag.find(['h2', 'h3']).get_text(strip=True).casefold() == 'guidance')), None)
    if guidance_box:
        guidance_box.clear()
        heading = soup.new_tag('h2')
        heading.string = 'Guidance'
        content = soup.new_tag('p')
        content.string = '{{template_guidance}}'
        guidance_box.extend([heading, content])
    fields = []
    for tag in [soup.body, *soup.body.find_all(True)]:
        original_class = ' '.join(tag.get('class', []))
        bar = bool(re.search(r'bar|progress|fill', original_class, re.I))
        attrs = {}
        if tag.get('class'):
            attrs['class'] = [classes[c] for c in tag['class']]
        if tag.get('id'):
            attrs['id'] = ids[tag['id']]
        if tag.get('style'):
            attrs['style'] = _declarations(tag['style'], bar=bar)
        if tag.name == 'a' and tag.get('href', '').startswith('#') and tag['href'][1:] in ids:
            attrs['href'] = '#' + ids[tag['href'][1:]]
        for attr in ('colspan', 'rowspan'):
            if str(tag.get(attr, '')).isdigit() and int(tag[attr]) <= 100:
                attrs[attr] = tag[attr]
        tag.attrs = attrs
        for text in list(tag.children):
            if not isinstance(text, NavigableString) or not text.strip():
                continue
            normalized = ' '.join(str(text).split())
            if normalized == '{{template_guidance}}':
                continue
            # Category names inside data rows are data too, even if they are
            # familiar design vocabulary (e.g. Personnel). Only structural
            # headings/navigation can retain standard labels.
            structural_label = tag.name in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'th', 'dt', 'summary', 'a'} and not tag.find_parent(['td', 'dd'])
            label = LABELS.get(normalized.casefold()) if structural_label else None
            if label:
                text.replace_with(label)
                continue
            field_id = f'field_{len(fields)+1}'
            previous = tag.find_previous(['th', 'dt', 'h2', 'h3'])
            hint = LABELS.get(previous.get_text(' ', strip=True).casefold(), '') if previous else ''
            cell = tag if tag.name == 'td' else tag.find_parent('td')
            if cell:
                headers = cell.find_parent('table').select('thead th')
                column = len(cell.find_previous_siblings(['td', 'th']))
                if column < len(headers):
                    hint = LABELS.get(headers[column].get_text(' ', strip=True).casefold(), '')
            kind = 'Heading' if tag.name in {'h1', 'h2', 'h3', 'h4'} else 'Value' if tag.name in {'td', 'dd'} else 'Text'
            fields.append({'id': field_id, 'label': hint or f'{kind} {len(fields)+1}', 'bar': bar})
            text.replace_with('{{' + field_id + '}}')
            if bar:
                # Internal field marker is applied only after sanitizing a template.
                tag['data-template-bar'] = field_id
    if len(fields) > 500:
        raise HTTPException(422, 'This design has too many fields. Split it into smaller templates.')
    # Drop all head metadata from the original; reconstruct our own policy/title.
    styles = ''.join(str(style) for style in soup.find_all('style'))
    for style in soup.find_all('style'):
        style.extract()
    shell = styles + str(soup.body)
    tables = []
    shell_soup = BeautifulSoup(shell, 'html.parser')
    for table in shell_soup.find_all('table'):
        rows = [row for row in table.find_all('tr') if row.find('td') and row.find_parent('table') is table]
        if not rows:
            continue
        columns = max(len(row.find_all(['td', 'th'], recursive=False)) for row in rows)
        if not columns or columns > 40:
            continue
        table_id = f'table_{len(tables)+1}'
        table['data-template-table'] = table_id
        field_ids = re.findall(r'\{\{(field_\d+)\}\}', ''.join(str(row) for row in rows))
        headers = [cell.get_text(' ', strip=True) for cell in table.select('thead th')]
        tables.append({'id': table_id, 'columns': columns, 'headers': headers, 'field_ids': field_ids})
    return {'html': str(shell_soup), 'fields': fields, 'tables': tables}


def prepare(db, user_id, html):
    draft = design(html)
    key = hashlib.sha256((user_id + json.dumps(draft, sort_keys=True)).encode()).hexdigest()[:32]
    db.page_template_drafts.find_one_and_update({'_id': key}, {'$setOnInsert': {
        **draft, 'user_id': user_id, 'created_at': datetime.now(timezone.utc),
    }}, upsert=True, return_document=ReturnDocument.AFTER)
    return {'draft_id': key, **draft, 'preview_html': render(draft, {})[0]}


def save(db, user_id, owner_name, body):
    draft = db.page_template_drafts.find_one({'_id': body.draft_id, 'user_id': user_id})
    if not draft:
        raise HTTPException(404, 'Template preview not found. Prepare it again.')
    if not body.name.strip():
        raise HTTPException(422, 'Name the template before saving.')
    fields = [{**field, 'label': body.field_labels.get(field['id'], field['label']).strip()[:160]} for field in draft['fields']]
    identity = json.dumps([user_id, body.draft_id, body.name.strip(), body.description, body.guidance, fields], sort_keys=True)
    uuid = hashlib.sha256(identity.encode()).hexdigest()[:32]
    doc = db.page_templates.find_one_and_update({'uuid': uuid}, {'$setOnInsert': {
        'uuid': uuid, 'user_id': user_id, 'owner_name': owner_name, 'team_id': None,
        'name': body.name.strip(), 'description': body.description.strip(), 'guidance': body.guidance.strip(),
        'html': draft['html'], 'fields': fields, 'tables': draft.get('tables', []), 'deleted_at': None, 'created_at': datetime.now(timezone.utc),
    }}, upsert=True, return_document=ReturnDocument.AFTER)
    if doc.get('deleted_at'):
        raise HTTPException(409, 'This template was deleted. Choose a new name to save a new template.')
    return doc


def get(db, uuid):
    doc = db.page_templates.find_one({'uuid': uuid, 'deleted_at': None})
    if not doc:
        raise HTTPException(404, 'Template not found')
    return doc


def metadata(doc, user_id):
    return {key: doc.get(key) for key in ('uuid', 'name', 'description', 'owner_name', 'team_id', 'created_at')} | {
        'can_manage': doc['user_id'] == user_id,
    }


def render(template, values, table_values=None):
    soup = BeautifulSoup(template['html'], 'html.parser')
    table_values = table_values or {}
    filled = 0
    filled_cells = set()
    for table in soup.select('[data-template-table]'):
        table_id = table.attrs.pop('data-template-table')
        if table_id not in table_values:
            continue
        old_rows = [row for row in table.find_all('tr') if row.find('td') and row.find_parent('table') is table]
        if not old_rows:
            continue
        prototype = max(old_rows, key=lambda row: len(row.find_all(['td', 'th'], recursive=False)))
        parent = prototype.parent
        for values_row in table_values[table_id]:
            row = deepcopy(prototype)
            for cell, value in zip(row.find_all(['td', 'th'], recursive=False), values_row):
                cell.clear()
                cell.string = value if value is not None else MISSING
                filled_cells.add(id(cell))
                if value is not None:
                    filled += 1
            parent.append(row)
        for row in old_rows:
            row.decompose()
    has_guidance = '{{template_guidance}}' in template['html']
    for text in list(soup.find_all(string=True)):
        if text.parent.name == 'style' or id(text.parent) in filled_cells:
            continue
        def substitute(match):
            nonlocal filled
            if match[1] == 'template_guidance':
                return template.get('guidance') or 'Reusable guidance'
            value = values.get(match[1])
            if value is not None:
                filled += 1
            return value if value is not None else MISSING
        text.replace_with(re.sub(r'\{\{(field_\d+|template_guidance)\}\}', substitute, str(text)))
    numeric = {}
    for key, value in values.items():
        if key not in {field['id'] for field in template['fields'] if field.get('bar')}:
            continue
        if re.fullmatch(r'[$€£]?\s*[\d,]+(?:\.\d+)?%?', value.strip()):
            numeric[key] = float(re.sub(r'[^\d.]', '', value))
    maximum = max(numeric.values(), default=0)
    for bar in soup.select('[data-template-bar]'):
        key = bar.attrs.pop('data-template-bar')
        width = 100 * numeric.get(key, 0) / maximum if maximum else 0
        bar['style'] = re.sub(r'(?:width|height):[^;]*;?', '', bar.get('style', '')) + (f';width:{width:.3f}%;overflow:visible' if key in numeric else ';width:auto;background:none;border:1px dashed gray')
    if template.get('guidance') and not has_guidance:
        guidance = soup.new_tag('aside')
        title = soup.new_tag('h2')
        title.string = 'Guidance'
        guidance.append(title)
        body = soup.new_tag('p')
        body.string = template['guidance']
        guidance.append(body)
        soup.append(guidance)
    html, _ = artifacts.clean_html(str(soup), template.get('name', 'Page preview'))
    return html, filled


def fill(template, document, supplied, supplied_tables=None):
    text = ' '.join((document.raw_text or '').split())
    if document.processing or getattr(document, 'soft_deleted', False) or not text:
        raise HTTPException(422, 'Choose a processed file with readable text.')
    ids = {field['id'] for field in template['fields']}
    def checked(value, quote):
        value, quote = ' '.join(value.split()), ' '.join(quote.split())
        numeric = re.fullmatch(r'[-+]?[$€£]?\s*\d[\d,.]*%?', value)
        boundary = (r'(?<![\w.,+\-$€£])', r'(?!\w|[.,]\d|%)') if numeric else (r'(?<!\w)', r'(?!\w)')
        if not value or not quote or quote not in text or not re.search(boundary[0] + re.escape(value) + boundary[1], quote):
            raise HTTPException(422, 'A supplied value is not supported by its quote in the selected file. Omit unavailable values.')
        return value
    tables = {table['id']: table for table in template.get('tables', [])}
    table_values = {}
    for supplied_table in supplied_tables or []:
        if supplied_table.table_id not in tables or supplied_table.table_id in table_values:
            raise HTTPException(422, 'Use each template table once, with its exact identifier.')
        table = tables[supplied_table.table_id]
        rows = []
        for row in supplied_table.rows:
            if len(row) != table['columns']:
                raise HTTPException(422, 'Keep the template table columns; use an empty cell for missing information.')
            rows.append([checked(cell.value, cell.quote) if cell else None for cell in row])
        if not rows:
            rows = [[None] * table['columns']]
        table_values[table['id']] = rows
        ids -= set(table['field_ids'])
    values = {}
    for item in supplied:
        value, quote = ' '.join(item.value.split()), ' '.join(item.quote.split())
        if item.field_id not in ids or item.field_id in values:
            raise HTTPException(422, 'Use each template field once, with its exact field identifier.')
        values[item.field_id] = checked(value, quote)
    html, count = render(template, values, table_values)
    total = len(ids) + sum(len(row) for rows in table_values.values() for row in rows)
    check = {'filled': count, 'missing': total - count, 'retained': 0,
             'source_title': document.title, 'source_document_uuid': document.uuid, 'template_name': template['name']}
    return html, check
