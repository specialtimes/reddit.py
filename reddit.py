#!/usr/bin/python3.5

from imgurdownloader import ImgurDownloader
import requests
import urllib.request
import argparse
from bs4 import BeautifulSoup
import re
import glob
import subprocess
import os
import json
import peewee
import hashlib
import shutil
import itertools
import logging
import time
from multiprocessing.dummy import Pool as ThreadPool

logging.basicConfig(format='%(asctime)s|%(levelname)s|%(message)s',filename='reddit.log',level=logging.INFO)

parser = argparse.ArgumentParser()
parser.add_argument("user")

args = parser.parse_args()

db = peewee.MySQLDatabase("reddit", host="localhost", user="reddit", passwd="reddit")

class FileData(peewee.Model):
  user = peewee.CharField()
  md5 = peewee.CharField()
  filename = peewee.CharField()
  filetype = peewee.CharField()
  class Meta:
    database = db

class UserData(peewee.Model):
  user = peewee.CharField()
  latest = peewee.CharField()
  class Meta:
    database = db


# https://stackoverflow.com/a/3431838
def md5(fname):
  hash_md5 = hashlib.md5()
  with open(fname, "rb") as f:
    for chunk in iter(lambda: f.read(4096), b""):
      hash_md5.update(chunk)
  return hash_md5.hexdigest()


def verifyCreateDir(user, dltype):
  if not os.path.exists(user + "/" + dltype):
    try:
      os.makedirs(user + "/" + dltype)
    except:
      pass


def bestUrl(list1, list2, urls):
  slist1 = []
  slist2 = []
  for i in list2:
    for i2 in urls:
      if i in i2:
        slist1.append(i2)
  for i in list1:
    for i2 in slist1:
      if i in i2:
        slist2.append(i2)
  return slist2[0]


def checkDupeHash(filepath):
  filehash = md5(filepath)
  if filehash == "d835884373f4d6c8f24742ceabe74946":
    return "IMGUR_404: {}".format(filepath.split(r'/')[-1])
  try:
    FileData.select().where(FileData.md5 == filehash).get()
    return "IMAGE_HASH_EXISTS: {}".format(filehash)
  except:
    raise


def checkDupeFilename(filename):
  try:
    FileData.select().where(FileData.filename == filename).get()
    return "{}: file already exists".format(filename)
  except:
    raise


def addFiletoDB(user, filename, dltype):
  filehash = md5(user + "/" + dltype + "/" + filename)
  FileData(user=user, md5=filehash, filename=filename, filetype=dltype).save()


def downloadFile(url, filename, user, dltype):
  filedest = os.path.join(user + "/" + dltype + "/" + filename)
  if not glob.glob(re.sub('\.[^.]*$', '', filedest) + "*"):
    try:
      urllib.request.urlretrieve (url, "/tmp/" + filename)
      logging.info(filename)
      try:
        logging.info(checkDupeHash("/tmp/" + filename))
        os.remove("/tmp/" + filename)
      except:
        verifyCreateDir(user, dltype)
        print ("Downloading to: {} From: {}".format(filedest, url))
        logging.info("FILE_DOWNLOAD: {}".format(user + "/" + dltype + "/" + filename))
        shutil.move("/tmp/" + filename, filedest)
        addFiletoDB(user, filename, dltype)
    except Exception as e:
      logging.info("FAILED_DOWNLOAD_URL: {} EXCEPTION: {}".format(url, e))
      pass
  else:
    logging.info("FILE_EXISTS: {}".format(user + "/" + dltype + "/" + filename))


def imgurDownload(url, user):
  vids = [ "gif", "gifv", "mp4" ]
  try:
    downloader = ImgurDownloader(url)
    if downloader.num_images() == 1:
      verifyCreateDir(user, "images")
      if any(x in url for x in vids) or any(x in str(downloader.list_extensions()) for x in vids):
        dltype = "videos"
      else:
        dltype = "images"
      if downloader.imageIDs[0][0] == "":
        filename = url.split(r'/')[-1]
      else:
        if "gif" in downloader.imageIDs[0][1]:
          filename = downloader.imageIDs[0][0] + ".mp4"
        else:
          filename = downloader.imageIDs[0][0] + downloader.imageIDs[0][1]
      url = "https://i.imgur.com/" + filename
      downloadFile(url, filename, user, dltype)
    elif downloader.num_images() == 0:
      logging.info("IMGUR_EMPTY_ALBUM: {}".format(url))
      return
    else:
      if not os.path.exists(user + "/albums/" + downloader.get_album_key()):
        try:
          downloader.save_images(user + "/albums/" + downloader.get_album_key())
          print ("Downloading to: {} From: {}".format(user + "/albums/" + downloader.get_album_key(), url))
          logging.info("IMGUR_ALBUM_DOWNLOAD: {}".format(url))
        except Exception as e:
          logging.info("IMGUR_ALBUM_EXCEPTION: {}".format(e))
          pass
      else:
        logging.info("ALBUM_EXISTS: {}".format(user + "/albums/" + downloader.get_album_key()))
  except Exception as e:
    logging.info("IMGUR_EXCEPTION: {}".format(e))
    pass


def gfycatDownload(url, user):
  gfycathost = [ "giant.gfycat.com", "fat.gfycat.com", "zippy.gfycat.com", "thumbs.gfycat.com" ]
  gfycatformat = [ "mp4", "webm" ]
  itemlist = []
  html = requests.get(url)
  if html.ok:
    if "text/html" not in html.headers['content-type'].lower():
      url = "https://www.gfycat.com/" + re.findall('com\/(.+?)[$-@.&_?]', url)[0]
      html = requests.get(url)
    soup = BeautifulSoup(html.content, "html5lib")
    for video in soup(["video"]):
      for vobj in video(["source"]):
        itemlist.append(vobj.attrs['src'])
    if not itemlist:
      return
    dlurl = bestUrl(gfycathost, gfycatformat, itemlist)
    downloadFile(dlurl, dlurl.split(r'/')[-1], user, "videos")
  else:
    logging.info("USER: {} URL: {} STATUS_CODE: {} REASON: {}".format(user, url, html.status_code, html.reason))


def reddituploadsDownload(url, user):
  try:
    downloadFile(re.sub('amp;', '', url), re.findall('.com\/(.*)\?', url)[0], user, "images")
    ext = subprocess.run(['file','--brief','--mime-type', user + "/images/" + re.findall('.com\/(.*)\?', url)[0]], stdout=subprocess.PIPE)
    os.rename(user + "/images/" + re.findall('.com\/(.*)\?', url)[0], user + "/images/" + re.findall('.com\/(.*)\?', url)[0] + "." + bytes.decode(ext.stdout.split(b'\n')[0].split(b'/')[1]))
  except:
    pass


def pornhubDownload(url, user):
  html = requests.get(url)
  try:
    videos = re.search(r"var flashvars_[0-9]{9}\s*=\s*(.*);", html.content.decode("utf-8")).group(1)
    jvideos = json.loads(videos)
    for i in jvideos['mediaDefinitions']:
      if i['defaultQuality'] == True:
        downloadFile(i['videoUrl'], re.search('[0-9]{6}/[0-9]{2}/[0-9]{9}/(.*)\?', i['videoUrl']).group(1), user, "videos")
  except:
    pass


def eromeDownload(url, user):
  res = [ "1080", "720", "480" ]
  itemlist = {}
  html = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_6_8) AppleWebKit/534.30 (KHTML, like Gecko) Chrome/12.0.742.112 Safari/534.30"})
  if html.ok:
    soup = BeautifulSoup(html.content, "html5lib")
    for i in res:
      for source in soup(["source"]):
        if i == source['res']:
          downloadFile("https:" + source['src'], source['src'].split(r'/')[-1], user, "videos")


def findIndexStart(user):
  try:
    return UserData.select().where(UserData.user == user).get().latest
  except:
    return "0"


def updateLatest(user, latest):
  try:
    record = UserData.select().where(UserData.user == user).get()
    record.latest = latest
    record.save()
  except:
    record = UserData(user=user, latest=latest).save()


def undefinedDownload(url, user):
  url = re.sub('amp;', '', url)
  try:
    html = requests.head(url, timeout=5)
    try:
      html.headers['content-type']
      if "text" not in html.headers['content-type'].lower():
        if any(x in html.headers['content-type'] for x in [ "gif", "gifv", "mp4" ]):
          dltype = "videos"
        else:
          dltype = "images"
        downloadFile(url, url.split(r'/')[-1].split(r'.')[0] + "." + html.headers['content-type'].split(r'/')[-1], user, dltype)
    except:
      pass
  except:
    pass

def splitJobs(user, url):
  if "imgur" in url:
    imgurDownload(url, user)
  elif "i.redd.it" in url:
    downloadFile(url, url.split(r'/')[-1], user, "images")
  elif "gfycat" in url:
    gfycatDownload(url, user)
  elif "pornhub" in url:
    pornhubDownload(url, user)
  elif "erome" in url:
    eromeDownload(url, user)
  elif "reddituploads.com" in url:
    reddituploadsDownload(url, user)
  else:
    undefinedDownload(url, user)

timestart = time.time()
print("Building URL list.")
startUTC = findIndexStart(args.user)
r = requests.get('https://elastic.pushshift.io/_search/?q=(author:' + args.user + ' AND created_utc:>' + startUTC + ')&sort=created_utc:asc&size=100', headers={'User-Agent': 'botman 1.0'})
urls = []

while r.json()['hits']['total'] > 0:
  for post in r.json()['hits']['hits']:
    if post['_type'] == "comments":
      url = re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', post['_source']['body'])
    if post['_type'] == "submissions":
      url = [post['_source']['url']]
    if url:
      for i in url:
        i = i.replace("http://", "https://")
        i = re.sub('[)!?,*.:]{1,3}$', '', i)
        if i not in urls:
          urls.append(i)
  r = requests.get('https://elastic.pushshift.io/_search/?q=(author:' + args.user + ' AND created_utc:>' + str(post['_source']['created_utc']) + ')&sort=created_utc:asc&size=100', headers={'User-Agent': 'botman 1.0'})


if len(urls) > 0:
  print("Discovered {} new urls for {}, beginning download..".format(len(urls), args.user))
    
  logging.info("Beginning download for {} with {} discovered addresses.".format(args.user, len(urls)))
  
  # https://stackoverflow.com/a/28463266
  if __name__ == '__main__':
    pool = ThreadPool(4)
    
    pool.starmap(splitJobs, zip(itertools.repeat(args.user), urls))
    
    pool.close()
    pool.join()
    
    logging.info("Processing complete, took {}".format(time.time()-timestart))
  
  updateLatest(args.user, str(post['_source']['created_utc']))

else:
  print("No new objects found.")
