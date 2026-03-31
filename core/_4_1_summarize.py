import json
from core._shared_prompts import get_summary_prompt
from core.utils import *
from core.utils.models import _3_2_SPLIT_BY_MEANING, _4_1_TERMINOLOGY
from core._shared_terminology import (
    build_relevant_terms_prompt,
    load_custom_terms,
    load_terminology_terms,
    merge_terms,
)

CUSTOM_TERMS_PATH = 'custom_terms.xlsx'

def combine_chunks():
    """Combine the text chunks identified by whisper into a single long text"""
    with open(_3_2_SPLIT_BY_MEANING, 'r', encoding='utf-8') as file:
        sentences = file.readlines()
    cleaned_sentences = [line.strip() for line in sentences]
    combined_text = ' '.join(cleaned_sentences)
    return combined_text[:load_key('summary_length')]  #! Return only the first x characters

def search_things_to_note_in_prompt(sentence):
    return build_relevant_terms_prompt(sentence, load_terminology_terms())

def get_summary():
    src_content = combine_chunks()
    custom_terms_json = load_custom_terms(CUSTOM_TERMS_PATH)
    if custom_terms_json["terms"]:
        rprint(f"📖 Custom Terms Loaded: {len(custom_terms_json['terms'])} terms")
        rprint("📝 Terms Content:", json.dumps(custom_terms_json, indent=2, ensure_ascii=False))
    summary_prompt = get_summary_prompt(src_content, custom_terms_json)
    rprint("📝 Summarizing and extracting terminology ...")
    
    def valid_summary(response_data):
        required_keys = {'src', 'tgt', 'note'}
        if 'terms' not in response_data:
            return {"status": "error", "message": "Invalid response format"}
        for term in response_data['terms']:
            if not all(key in term for key in required_keys):
                return {"status": "error", "message": "Invalid response format"}   
        return {"status": "success", "message": "Summary completed"}

    summary = ask_gpt(summary_prompt, resp_type='json', valid_def=valid_summary, log_title='summary')
    summary = {
        "theme": summary.get("theme", ""),
        "terms": merge_terms(summary, custom_terms_json)["terms"],
    }
    
    with open(_4_1_TERMINOLOGY, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=4)

    rprint(f'💾 Summary log saved to → `{_4_1_TERMINOLOGY}`')

if __name__ == '__main__':
    get_summary()
