import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HEXSOUND_NO_MODAL"] = "1"  # janelas modais do app retornam 'cancelado' na hora: um teste esquecido nunca trava a suíte
