import json, argparse, statistics
# NOTE: replace stubs with real retriever calls.
def retrieve(q, k): return ["docA","docB","docC","docD","docE"][:k]
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--gold'); ap.add_argument('--k',type=int,default=5); ap.add_argument('--report'); a=ap.parse_args()
    gold=[json.loads(l) for l in open(a.gold)]
    hits=[]; mrr=[]
    for row in gold:
        docs=retrieve(row["query"], a.k)
        if row["answer_doc"] in docs:
            hits.append(1); mrr.append(1.0/(docs.index(row["answer_doc"])+1))
        else:
            hits.append(0); mrr.append(0.0)
    out={"recall_at_"+str(a.k): sum(hits)/len(hits), "mrr": statistics.fmean(mrr)}
    print(out); 
    if a.report: json.dump(out, open(a.report,"w"), indent=2)
if __name__=="__main__": main()
