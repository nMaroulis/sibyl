import spacy
# SpaCy
from spacy.lang.en.stop_words import STOP_WORDS
from string import punctuation
from collections import Counter
from heapq import nlargest
# Sumy
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.text_rank import TextRankSummarizer
from sumy.summarizers.lsa import LsaSummarizer
# from gensim.summarize import summarizer


def get_text_summary(model='sumy', articles=None):
    doc = ""

    if articles is not None:
        if len(list(articles)) > 0:
            for article in articles:
                doc += article[0] + ". " + article[1]
                for p in article[3]:
                    doc += p
        if model == 'spacy':
            return spacy_text_summarizer(doc)
        elif model == 'gensim':
            return gensim_text_summarizer(doc)
        elif model == 'sumy':
            return sumy_text_summarizer(doc)
        else:  # DEFAULT
            gensim_text_summarizer(doc)
    else:
        return []


def gensim_text_summarizer(doc):
    # summary = summarize(doc)
    return []


def sumy_text_summarizer(doc, summ_type='lsa'):
    parser = PlaintextParser.from_string(doc, Tokenizer("english"))

    if summ_type == 'textrank':
        summarizer = TextRankSummarizer()  # TextRank Summarizer
        summary = summarizer(parser.document, 2)
    else:
        summarizer_lsa = LsaSummarizer()
        summary = summarizer_lsa(parser.document, 4) # LSA Summarizer
    text_summary = ""
    for sentence in summary:
        text_summary += str(sentence)

    return text_summary


def spacy_text_summarizer(doc):

    nlp = spacy.load('en_core_web_sm')
    doc = nlp(doc)
    print("Reporter :: Spacy Model :: sentences_num:", len(list(doc.sents)), ' doc characters:', len(doc))

    keyword = []
    stopwords = list(STOP_WORDS)
    pos_tag = ['PROPN', 'ADJ', 'NOUN', 'VERB']
    for token in doc:
        if (token.text in stopwords or token.text in punctuation):
            continue
        if (token.pos_ in pos_tag):
            keyword.append(token.text)

    freq_word = Counter(keyword)

    max_freq = Counter(keyword).most_common(1)[0][1]
    for word in freq_word.keys():
        freq_word[word] = (freq_word[word] / max_freq)
    freq_word.most_common(3)

    sent_strength = {}
    for sent in doc.sents:
        for word in sent:
            if word.text in freq_word.keys():
                if sent in sent_strength.keys():
                    sent_strength[sent] += freq_word[word.text]
                else:
                    sent_strength[sent] = freq_word[word.text]
    summarized_sentences = nlargest(3, sent_strength, key=sent_strength.get)
    final_sentences = [w.text for w in summarized_sentences]
    summary = ' '.join(final_sentences)
    return summary
