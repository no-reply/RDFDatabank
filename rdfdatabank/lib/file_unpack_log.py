import subprocess

from datetime import datetime, timedelta
import time
import os

from redis import Redis

from uuid import uuid4

from rdfdatabank.lib.utils import create_new, munge_manifest, test_rdf

#import checkm
from zipfile import ZipFile, BadZipfile as BZ

zipfile_root = "zipfile:"

class BadZipfile(Exception):
    """Cannot open zipfile using commandline tool 'unzip' to target directory"""
   
def check_file_mimetype(real_filepath, mimetype):
    if os.path.islink(real_filepath):
        real_filepath = os.readlink(real_filepath)
    p = subprocess.Popen("file -ib %s" %(real_filepath), shell=True, stdout=subprocess.PIPE)
    output_file = p.stdout
    output_str = output_file.read()
    if mimetype in output_str:
        return True
    else:
        return False
        
def get_zipfiles_in_dataset(dataset):
    derivative = dataset.list_rdf_objects("*", "ore:aggregates")
    #print "derivative ", derivative
    #print "derivative values", derivative.values()[0]
    zipfiles = {}
    if derivative and derivative.values() and derivative.values()[0]:
        for file_uri in derivative.values()[0]:
            filepath = file_uri[len(dataset.uri)+1:]
            real_filepath = dataset.to_dirpath(filepath)
            if os.path.islink(real_filepath):
                real_filepath = os.readlink(real_filepath)
            #print "file_uri : ", file_uri
            #print "filepath : ", filepath
            #print "real_filepath : ", real_filepath
            if check_file_mimetype(real_filepath, 'application/zip'): 
                (fn, ext) = os.path.splitext(filepath)
                zipfiles[filepath]="%s-%s"%(dataset.item_id, fn)
    return zipfiles
        
def store_zipfile(silo, target_item_uri, POSTED_file, ident):
    zipfile_id = get_next_zipfile_id(silo.state['storage_dir'])
    while(silo.exists("%s%s" % (zipfile_root, zipfile_id))):
        zipfile_id = get_next_zipfile_id(silo.state['storage_dir'])
    
    #zip_item = silo.get_item("%s%s" % (zipfile_root, zipfile_id))
    zip_item = create_new(silo, "%s%s" % (zipfile_root, zipfile_id), ident)
    zip_item.add_triple("%s/%s" % (zip_item.uri, POSTED_file.filename.lstrip(os.sep)), "dcterms:hasVersion", target_item_uri)
    zip_item.put_stream(POSTED_file.filename, POSTED_file.file)
    try:
        POSTED_file.file.close()
    except:
        pass
    zip_item.sync()
    return zip_item

def read_zipfile(filepath):
    try:
        tmpfile = ZipFile(filepath, "r")
    except BZ:
        raise BadZipfile

    # list filenames
    #list_of_files = tmpfile.namelist()
    
    # file information
    zipfile_contents = {}
    for info in tmpfile.infolist():
        zipfile_contents[info.filename] = (info.file_size, info.date_time)
    tmpfile.close()
    return zipfile_contents

def read_file_in_zipfile(filepath, filename):
    try:
        tmpfile = ZipFile(filepath, "r")
    except BZ:
        raise BadZipfile

    try:
        fileinfo = tmpfile.getinfo(filename)
    except KeyError:
        return False
    if fileinfo.file_size == 0:
        return 0

    # read file
    file_contents = None
    file_contents = tmpfile.read(filename)
    tmpfile.close()
    return file_contents

def get_file_in_zipfile(filepath, filename, targetdir):
    try:
        tmpfile = ZipFile(filepath, "r")
    except BZ:
        raise BadZipfile

    try:
        fileinfo = tmpfile.getinfo(filename)
    except KeyError:
        return False
    if fileinfo.file_size == 0:
        return 0

    # extract file
    targetfile = tmpfile.extract(filename, targetdir)
    tmpfile.close()
    return targetfile

def unzip_file(filepath, target_directory=None):
    #f = open("/tmp/python_out.log", "a")
    #f.write("\n--------------- In unzip file -------------------\n")
    #f.write("filepath : %s\n"%str(filepath))
    #f.write('-'*40+'\n')
    #f.close()
    # TODO add the checkm stuff back in
    if not target_directory:
        target_directory = "/tmp/%s" % (uuid4().hex)
    p = subprocess.Popen("unzip -qq -d %s %s" % (target_directory, filepath), shell=True, stdout=subprocess.PIPE)
    p.wait()
    if p.returncode != 0:
        raise BadZipfile
    else:
        return target_directory
     
def get_items_in_dir(items_list, dirname, fnames):
    for fname in fnames:
        items_list.append(os.path.join(dirname,fname))
    return

def unpack_zip_item(target_dataset, current_dataset, zip_item, silo, ident):
    f = open('/opt/rdfdatabank/src/logs/runtimes.log', 'a')
    hr = "-"*80 + '\n'
    f.write(hr)
    f.write("file_unpack - unpack_zip_item\n")
    f.write("Unpacking %s in %s TO %s\n"%(zip_item, current_dataset.uri, target_dataset.uri))
    filepath = current_dataset.to_dirpath(zip_item)
    if os.path.islink(filepath):
        filepath = os.readlink(filepath)

    # -- Step 1 -----------------------------
    tic1 = time.mktime(time.gmtime())    
    unpacked_dir = unzip_file(filepath)
    toc = time.mktime(time.gmtime())
    f.write("1. Time to unpack: %d\n"%(toc-tic1))
    f.close()

    # -- Step 2 -----------------------------
    f = open('/opt/rdfdatabank/src/logs/runtimes.log', 'a')
    tic = time.mktime(time.gmtime())    
    file_uri = current_dataset.uri
    if not file_uri.endswith('/'):
        file_uri += '/'
    file_uri = "%s%s"%(file_uri,zip_item)
     
    items_list = []
    os.path.walk(unpacked_dir,get_items_in_dir,items_list)
    toc = time.mktime(time.gmtime())
    f.write("2. Time to walk: %d\n"%(toc-tic))
    f.close()

    # -- Step 3 -----------------------------
    f = open('/opt/rdfdatabank/src/logs/runtimes.log', 'a')
    tic = time.mktime(time.gmtime())    
    manifest_str = None
    #Read manifest    
    for i in items_list:
        if 'manifest.rdf' in i and os.path.isfile(i):
            F = open(i, 'r')
            manifest_str = F.read()
            F.close()
            items_list.remove(i)
            os.remove(i)
            break
    toc = time.mktime(time.gmtime())
    f.write("3. Time to read manifest: %d\n"%(toc-tic))
    f.close()

    # -- Step 4 -----------------------------
    f = open('/opt/rdfdatabank/src/logs/runtimes.log', 'a')
    tic = time.mktime(time.gmtime())    
    #Copy unpacked dir as new version
    target_dataset.move_directory_as_new_version(unpacked_dir)
    toc = time.mktime(time.gmtime())
    f.write("4. Time to move unpacked file: %d\n"%(toc-tic))
    f.close()

    # -- Step 5 -----------------------------
    f = open('/opt/rdfdatabank/src/logs/runtimes.log', 'a')
    tic = time.mktime(time.gmtime())    
    #Add type and isVersionOf metadata
    target_dataset.add_namespace('oxds', "http://vocab.ox.ac.uk/dataset/schema#")
    target_dataset.add_triple(target_dataset.uri, u"rdf:type", "oxds:Grouping")
    target_dataset.add_triple(target_dataset.uri, "dcterms:isVersionOf", file_uri)
    #TODO: Adding the following metadata again as moving directory deletes all this information. Need to find a better way
    embargoed_until_date = (datetime.now() + timedelta(days=365*70)).isoformat()
    target_dataset.add_triple(target_dataset.uri, u"oxds:isEmbargoed", 'True')
    target_dataset.add_triple(target_dataset.uri, u"oxds:embargoedUntil", embargoed_until_date)
    target_dataset.add_triple(target_dataset.uri, u"dcterms:identifier", target_dataset.item_id)
    target_dataset.add_triple(target_dataset.uri, u"dcterms:creator", ident)
    target_dataset.add_triple(target_dataset.uri, u"dcterms:created", datetime.now())
    target_dataset.add_triple(target_dataset.uri, u"oxds:currentVersion", target_dataset.currentversion)
    #Adding ore aggregates
    unp_dir = unpacked_dir
    if not unp_dir.endswith('/'):
        unp_dir += '/'
    target_uri_base = target_dataset.uri
    if not target_uri_base.endswith('/'):
        target_uri_base += '/'
    for i in items_list:
        i = i.replace(unp_dir, '')
        target_dataset.add_triple(target_dataset.uri, "ore:aggregates", "%s%s"%(target_uri_base,i))
    target_dataset.add_triple(target_dataset.uri, u"dcterms:modified", datetime.now())
    target_dataset.sync()
    toc = time.mktime(time.gmtime())
    f.write("5. Time to add metadata: %d\n"%(toc-tic))
    f.close()

    # -- Step 6 -----------------------------
    f = open('/opt/rdfdatabank/src/logs/runtimes.log', 'a')
    tic = time.mktime(time.gmtime())    
    #Munge rdf
    #TODO: If manifest is not well formed rdf - inform user. Currently just ignored.
    if manifest_str and test_rdf(manifest_str):
        munge_manifest(manifest_str, target_dataset, manifest_type='http://vocab.ox.ac.uk/dataset/schema#Grouping')
    toc = time.mktime(time.gmtime())
    f.write("6. Time to munge rdf: %d\n"%(toc-tic))
     
    # -- Step 7 -----------------------------
    tic = time.mktime(time.gmtime())    
    target_dataset.sync()
    target_dataset.sync()
    target_dataset.sync()
    current_dataset.add_triple("%s/%s" % (current_dataset.uri, zip_item.lstrip(os.sep)), "dcterms:hasVersion", target_dataset.uri)
    current_dataset.sync()
    toc = time.mktime(time.gmtime())
    f.write("7. Time to Sync and unpadte parent manifest: %d\n"%(toc-tic))

    f.write(hr)
    f.write("Total Time: %d\n\n"%(toc-tic1))
    f.close()
    return True