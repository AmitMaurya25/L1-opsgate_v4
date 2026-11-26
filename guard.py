"""Input guardrails + redaction. Regex is ONE layer; retrieval/tool outputs are also treated as untrusted."""
import re
import config as C

INJ = re.compile(r"(ignore|disregard|forget)\s+(all |any |the )?(previous |prior |above |earlier )?(instructions|rules|guidelines)"
                 r"|reveal.{0,30}(system prompt|instructions)|\byou are now\b|developer mode|jailbreak|act as (an? )?(unrestricted|dan)", re.I)
SECRET = re.compile(r"\b(password|passwd|pwd|api[_ -]?key|secret|token|otp)\s*[:=]\s*\S+|sk-[A-Za-z0-9]{16,}|bearer\s+[a-z0-9._-]{20,}", re.I)
UNSAFE = re.compile(r"(bypass|disable|skip|turn off|ignore|get around).{0,30}(certificate|ssl|tls|antivirus|\bmfa\b|firewall|security)"
                    r"|share (my |the |your )?(password|mfa code)|keylogger|hack into|crack (a |the )?password", re.I)
HARM = re.compile(r"\b(bomb|kill (myself|him|her|someone)|suicide|self[- ]harm|weapon)\b", re.I)

MESSAGES = {
    'empty': 'Please type your IT question.',
    'too_long': f'That message is too long (limit {C.MAX_INPUT_CHARS} characters). Please shorten it.',
    'injection': 'Input rejected by security policy: I can only follow IT service-desk instructions.',
    'secret': 'Please do not share passwords, keys or tokens in chat. Remove them and describe the problem instead.',
    'unsafe': 'I cannot help bypass or disable security controls. I can suggest an approved fix or raise a ticket.',
    'harm': 'I can only help with IT support. If someone is in danger, please contact local emergency services.',
}

def check(text):
    """Return a block code or None."""
    if not text: return 'empty'
    if len(text) > C.MAX_INPUT_CHARS: return 'too_long'
    if INJ.search(text): return 'injection'
    if SECRET.search(text): return 'secret'
    if HARM.search(text): return 'harm'
    if UNSAFE.search(text): return 'unsafe'
    return None

def redact(text):
    t = SECRET.sub('[secret]', str(text))
    t = re.sub(r'[\w.+-]+@[\w-]+\.[\w.-]+', '[email]', t)
    return re.sub(r'\d{10,}', '[number]', t)
