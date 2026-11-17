from app.reader import decode
from app.pipeline import calculate
from app.errors import DomainError
import pytest
def test_sample_records(ctx):assert ctx['input_count']==45
def test_legacy_chinese(): # TRAP-01
    from app.config import SAMPLE
    assert '标准源' in decode(SAMPLE.with_name('legacy-gb18030.csv').read_bytes())
def test_structural_diagnostic(raw):assert any(q['原因码']=='COLUMNS' for q in calculate(raw+'a,b\n')['quarantine'])
def test_empty_rejected():
    with pytest.raises(DomainError):calculate('')
def test_sample_rows_keep_line(ctx):assert ctx['rows'][0]['行号']==2
def test_header_only(raw):
    with pytest.raises(DomainError):calculate(raw.splitlines()[0])
def test_input_keeps_parent(ctx):assert ctx['rows'][1]['parent']=='ROOT'

