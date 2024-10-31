from nltk import sent_tokenize
from nltk.sentiment import SentimentIntensityAnalyzer
from nltk import data, download

try:
    data.find('tokenizers/punkt_tab/english.pickle')
except LookupError:
    download('punkt_tab')


def get_text_sentiment(model='vader', articles=None):
    doc = ""

    if articles is not None:
        if len(list(articles)) > 0:
            for article in articles:
                doc += article[0] + ". " + article[1]
                for p in article[3]:
                    doc += p
        if model == 'vader':
            return vader_text_sentiment(doc)
        else:  # DEFAULT
            return vader_text_sentiment(doc)
    else:
        return 0


def vader_text_sentiment(doc):
    # nltk.download('vader_lexicon')
    sid = SentimentIntensityAnalyzer()  # Initialize VADER sentiment analyzer
    sentences = sent_tokenize(doc)  # Tokenize article into sentences

    # Aggregate sentiment scores
    aggregate_score = {'neg': 0.0, 'neu': 0.0, 'pos': 0.0, 'compound': 0.0}
    for sentence in sentences:
        scores = sid.polarity_scores(sentence)
        for key, value in scores.items():
            aggregate_score[key] += value

    # Normalize aggregate score
    num_sentences = len(sentences)
    aggregate_score = {key: value / num_sentences for key, value in aggregate_score.items()}
    res = round(aggregate_score['compound'], 2)
    return res
