"""Portage Python fidèle du Light10Stemmer de SAFAR (regex préfixe + radical + suffixe)."""
import re

_NON_ARABE = re.compile('[^a-zA-Z0-9ءآأؤإئابةتثجحخدذرزسشصضطظعغفقكلمنهويى]')
_HAMZA = re.compile('[ءآأؤإئ]')
_PATTERN = re.compile(
    '^(وال|فال|بال|بت|يت|لت|مت|تت|وت|ست|نت|بم|لم|وم|كم|فم|ال|لل|وي|لي|سي|في|وا|فا|لا|با|)'
    '(.+?)'
    '(ات|وا|تا|ون|وه|ان|تي|ته|تم|كم|هن|هم|ها|ية|تك|نا|ين|يه|ة|ه|ي|ا|)$')


def stem(mot: str) -> str:
    m = _NON_ARABE.sub('', mot)
    m = m.replace('ى', 'ي')
    m = _HAMZA.sub('ا', m)
    r = _PATTERN.search(m)
    return r.group(2) if r else ''
