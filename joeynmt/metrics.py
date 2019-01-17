# coding: utf-8

import sacrebleu
import numpy as np

def chrf(hypotheses, references, corpus=True):
    """
    Character F-score from sacrebleu

    :param hypotheses:
    :param references:
    :param corpus: if False, mean sentence-level metric
    :return:
    """
    if corpus:
        return sacrebleu.corpus_chrf(
                        hypotheses=hypotheses,
                        references=references)
    else:
        # mean of sentence metric
        total_chrf = 0
        num_hyps = 0
        for hyp, ref in zip(hypotheses, references):
            total_chrf += sacrebleu.corpus_chrf(
                        hypotheses=[hyp],
                        references=[ref])
            num_hyps += 1
        return total_chrf / max(num_hyps, 1)


def bleu(hypotheses, references, corpus=True):
    """
    Raw corpus BLEU from sacrebleu (without tokenization)

    :param hypotheses:
    :param references:
    :param corpus: if False, mean sentence-level metric
    :return:
    """
    if corpus:
        return sacrebleu.raw_corpus_bleu(
                    sys_stream=hypotheses,
                    ref_streams=[references]).score

    else:  # mean of sentence metric
        total_sbleu = 0
        num_hyps = 0
        for hyp, ref in zip(hypotheses, references):
            total_sbleu += sacrebleu.raw_corpus_bleu(
                sys_stream=[hyp],
                ref_streams=[[ref]]).score
            num_hyps += 1
        return total_sbleu / max(num_hyps, 1)


def token_accuracy(hypotheses, references, level="word"):
    """
    Compute the accuracy of hypothesis tokens: correct tokens / all tokens
    Tokens are correct if they appear in the same position in the reference.

    :param hypotheses:
    :param references:
    :return:
    """
    correct_tokens = 0
    all_tokens = 0
    split_char = " " if level in ["word", "bpe"] else ""
    assert len(hypotheses) == len(references)
    for h, r in zip(hypotheses, references):
        all_tokens += len(h)
        for h_i, r_i in zip(h.split(split_char), r.split(split_char)):
            # min(len(h), len(r)) tokens considered
            if h_i == r_i:
                correct_tokens += 1
    return (correct_tokens / all_tokens)*100 if all_tokens > 0 else 0.0


def sequence_accuracy(hypotheses, references):
    """
    Compute the accuracy of hypothesis tokens: correct tokens / all tokens
    Tokens are correct if they appear in the same position in the reference.

    :param hypotheses:
    :param references:
    :return:
    """
    assert len(hypotheses) == len(references)
    correct_sequences = sum([1 for (h, r) in zip(hypotheses, references)
                             if h == r])
    return (correct_sequences / len(hypotheses))*100 if len(hypotheses) > 0 \
        else 0.0


def f1_bin(hypotheses, references):
    """
    Compute F1 scores for binary predictions

    :param hypotheses: 1D numpy array of 0 and 1s
    :param references: 1D numpy array of 0 and 1s
    :return: f1_score for class 1, f1_score for class 2
    """
    assert hypotheses.size == references.size
    assert len(hypotheses.shape) == 1
    assert len(references.shape) == 1
    tp_1 = (hypotheses & references).sum()
    tp_0 = ((1 - hypotheses) & (1 - references)).sum()
    fp_1 = (hypotheses & ~references).sum()  # same as fn_0
    fn_1 = (~hypotheses & references).sum()  # same as fp_0
    assert tp_0 + tp_1 + fn_1 + fp_1 == hypotheses.size
    prec_1 = tp_1 / (tp_1 + fp_1)
    rec_1 = tp_1 / (tp_1 + fn_1)
    f1_1 = 2 * (prec_1 * rec_1) / (prec_1 + rec_1) if (
                                                      prec_1 + rec_1) > 0 else 0
    prec_0 = tp_0 / (tp_0 + fn_1)
    rec_0 = tp_0 / (tp_0 + fp_1)
    f1_0 = 2 * (prec_0 * rec_0) / (prec_0 + rec_0) if (
                                                      prec_0 + rec_0) > 0 else 0
    return f1_1, f1_0


def token_edit_reward(gold, pred, shifted=False):
    # print("Computing rewards")
    # print("gold", gold)
    # print("pred", pred)
    rewards = np.zeros_like(pred, dtype=float)
    assert gold.shape == pred.shape
    length = gold.shape[1]
    # TODO use length of translation (EOS), not batch
    # TODO use number of occurrences, penalize repetitions
    for j, (g, p) in enumerate(zip(gold, pred)):  # iterate over batch
        for k, (g_i, p_i) in enumerate(zip(g, p)):  # iterate over time
            if p_i == g_i:
                rewards[j, k] = 1.0
            elif p_i in g and shifted:
                # find new positions of p_i in g
                p_index = np.where(g == p_i)
                # select the position that is closest
                closest_dist = np.abs(np.min(k - p_index[0]))
                shift_reward = 1 - (closest_dist / length)
                rewards[j, k] = shift_reward
                # print("shift reward for moving {} pos.: {}".format(closest_dist, shift_reward))
            else:
                continue
    return rewards


def token_lcs_reward(gold, pred):
    # based on https://en.wikibooks.org/wiki/Algorithm_Implementation/Strings/Longest_common_substring#Python
    # idea from http://www.aclweb.org/anthology/P18-2052
    # TODO adapt if two second longest
    def longest_common_substring_rewards(pred, gold):
        m = [[0] * (1 + len(gold)) for i in range(1 + len(pred))]
        longest, x_longest = 0, 0
        rewards = np.zeros(len(pred))
        for x in range(1, 1 + len(pred)):
            for y in range(1, 1 + len(gold)):
                if pred[x - 1] == gold[y - 1]:
                    m[x][y] = m[x - 1][y - 1] + 1
                    if m[x][y] > longest:
                        longest = m[x][y]
                        x_longest = x
                else:
                    m[x][y] = 0
        rewards[x_longest - longest: x_longest] = 1
        #return pred[x_longest - longest: x_longest]
        return rewards
    all_rewards = np.zeros_like(pred, dtype=float)
    for j, (g, p) in enumerate(zip(gold, pred)):  # iterate over batch
        r = longest_common_substring_rewards(p, g)
        all_rewards[j] += r
    return all_rewards

def token_recall_reward(gold, pred):
    rewards = np.zeros_like(pred, dtype=float)
    for j, (g, p) in enumerate(zip(gold, pred)):  # iterate over batch
        for k, p_i in enumerate(p):  # iterate over time
            if p_i in g:
                rewards[j,k] = 1
    return rewards
