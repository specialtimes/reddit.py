#!/usr/bin/python3.5

from imgurdownloader.imgurdownloader import ImgurDownloader
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


def md5(fname):
  hash_md5 = hashlib.md5()
  with open(fname, "rb") as f:
    for chunk in iter(lambda: f.read(4096), b""):
      hash_md5.update(chunk)
  return hash_md5.hexdigest()


def verifyCreateDir(user, dltype):
  if not os.path.exists(user + "/" + dltype):
    os.makedirs(user + "/" + dltype)


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


def downloadFile(url, filename, user, dltype):
  filedest = os.path.join(user + "/" + dltype + "/" + filename)
  if glob.glob(filedest + "*"):
    print ("{}: {} already exists".format(dltype, filename))
    return
  else:
    try:
      FileData.select().where(FileData.filename == filename).get()
      print ("{}: {} already exists in db".format(dltype, filename))
      return
    except:
      try:
        urllib.request.urlretrieve (url, "/tmp/" + filename)
        filehash = md5("/tmp/" + filename)
        try:
          FileData.select().where(FileData.md5 == filehash).get()
          print ("{}: {} hash already exists in db".format(dltype, filename))
          FileData(user=user, md5=filehash, filename=filename, filetype=dltype).save()
          return
        except:
          verifyCreateDir(user, dltype)
          print ("Downloading to {}: {}".format(filedest, url))
          shutil.move("/tmp/" + filename, filedest)
          FileData(user=user, md5=filehash, filename=filename, filetype=dltype).save()
      except:
        print ("Failed {}: {}".format(dltype, e))
        pass


def imgurDownload(url, user):
  vids = [ "gif", "gifv", "mp4" ]
  try:
    downloader = ImgurDownloader(url)
    if downloader.num_images() == 1:
      verifyCreateDir(user, "images")
      if any(x in url for x in vids) or any(x in str(downloader.list_extensions()) for x in vids):
        folder = "videos"
      else:
        folder = "images"
      try:
        filename = downloader.save_images(user + "/" + folder + "/" )
        print ("Downloading to {}: {}".format(user + "/" + folder + "/" + filename[0][0], url))
      except Exception as e:
        print ("Imgur single: {}".format(e))
        pass
    else:
      try:
        downloader.save_images(user + "/albums/" + downloader.get_album_key())
        print ("Downloading to album: {}".format(url))
      except Exception as e:
        print ("Imgur album: {}".format(e))
        pass
  except Exception as e:
    print ("Imgur main: {}".format(e))
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
    print ("html error: {} {}".format(html.status_code, html.reason))

def reddituploadsDownload(url, user):
  try:
    downloadFile(re.sub('amp;', '', url), re.findall('.com\/(.*)\?', url)[0], user, "images")
    ext = subprocess.run(['file','--brief','--mime-type', user + "/images/" + re.findall('.com\/(.*)\?', url)[0]], stdout=subprocess.PIPE)
    os.rename(user + "/images/" + re.findall('.com\/(.*)\?', url)[0], user + "/images/" + re.findall('.com\/(.*)\?', i)[0] + "." + bytes.decode(ext.stdout.split(b'\n')[0].split(b'/')[1]))
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
          return


print("Building URL list.")
r = requests.get('https://elastic.pushshift.io/_search/?q=(author:' + args.user + ')&sort=created_utc:desc&size=100', headers={'User-Agent': 'botman 1.0'})
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
        i = re.sub('[)!?,.:]{1,2}$', '', i)
        if i not in urls:
          urls.append(i)
  r = requests.get('https://elastic.pushshift.io/_search/?q=(author:' + args.user + ' AND created_utc:<' + str(post['_source']['created_utc']) + ')&sort=created_utc:desc&size=100', headers={'User-Agent': 'botman 1.0'})

print("Discovered {} urls, beginning download..".format(len(urls)))

for i in urls:
  if "imgur" in i:
    imgurDownload(i, args.user)
  elif "i.redd.it" in i:
    downloadFile(i, i.split(r'/')[-1], args.user, "images")
  elif "gfycat" in i:
    gfycatDownload(i, args.user)
  elif "pornhub" in i:
    pornhubDownload(i, args.user)
  elif "erome" in i:
    eromeDownload(i, args.user)
  elif "reddituploads.com" in i:
    reddituploadsDownload(i, args.user)
