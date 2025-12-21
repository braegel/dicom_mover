- > % python ./dicom_query_compare.py --download-day today  --node gerald
Traceback (most recent call last):
  File "/Users/x42/git/dicom_mover/./dicom_query_compare.py", line 34, in <module>
    from pynetdicom.sop_class import (
    ...<3 lines>...
    )
ImportError: cannot import name 'VerificationSOPClass' from 'pynetdicom.sop_class' (/Users/x42/git/dicom_mover/lib/python3.13/site-packages/pynetdicom/sop_class.py)