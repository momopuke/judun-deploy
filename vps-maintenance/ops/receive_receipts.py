#!/usr/bin/env python3
"""Decrypt bounded RSA-OAEP receipt packets from GitHub job text.

The receiver private key is supplied by path and must never be committed.
Relay timestamps/titles do not establish the payload version or freshness.
"""
import argparse,base64,json,re,subprocess,tempfile,time,zlib
from pathlib import Path

def decode(log,key,minimum=11,max_age=1800):
    found=[];seen=set();now=time.time()
    for msg in re.findall(r'HOST_(?:RECENT_\d+_)?ENCRYPTED_REPORT_B64=([A-Za-z0-9+/=]{684})',log):
        if msg in seen:continue
        seen.add(msg)
        try:raw=base64.b64decode(msg,validate=True)
        except ValueError:continue
        if len(raw)!=512:continue
        with tempfile.TemporaryDirectory(prefix='sc-vps-decrypt-') as td:
            p=Path(td);(p/'in').write_bytes(raw)
            result=subprocess.run(['openssl','pkeyutl','-decrypt','-inkey',str(key),
                '-pkeyopt','rsa_padding_mode:oaep','-pkeyopt','rsa_oaep_md:sha256',
                '-pkeyopt','rsa_mgf1_md:sha256','-in',str(p/'in')],capture_output=True,timeout=8)
        if result.returncode:continue
        try:
            # The reporter compresses at most one small JSON object per packet.
            d=zlib.decompressobj();plain=d.decompress(result.stdout,6000)
            if d.unconsumed_tail or not d.eof or d.unused_data:continue
            obj=json.loads(plain)
            if not isinstance(obj,dict):continue
            if type(obj.get('ts'))!=int or not -90<=now-obj['ts']<=max_age:continue
            if type(obj.get('seq'))!=int or obj['seq']<minimum:continue
            if (obj.get('v'),obj.get('k')) not in ((17,'base'),(17,'detail'),(18,'maintenance')):continue
            found.append(obj)
        except (ValueError,zlib.error):continue
    return sorted(found,key=lambda d:(d['ts'],d['k']),reverse=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--key',required=True,type=Path)
    p.add_argument('--logs',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--minimum-sequence',type=int,default=11);p.add_argument('--max-age',type=int,default=1800)
    a=p.parse_args();items=decode(a.logs.read_text(encoding='utf-8-sig'),a.key,a.minimum_sequence,a.max_age)
    a.output.write_text(json.dumps(items,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'packets':items},ensure_ascii=False))
    return 0 if items else 2
if __name__=='__main__':raise SystemExit(main())
