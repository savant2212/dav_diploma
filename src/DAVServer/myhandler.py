#Copyright (c) 2010 Nazarenko Nikita (god@savant.su)
#
#This library is free software; you can redistribute it and/or
#modify it under the terms of the GNU Library General Public
#License as published by the Free Software Foundation; either
#version 2 of the License, or (at your option) any later version.
#
#This library is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#Library General Public License for more details.
#
#You should have received a copy of the GNU Library General Public
#License along with this library; if not, write to the Free
#Software Foundation, Inc., 59 Temple Place - Suite 330, Boston,
#MA 02111-1307, USA

from DAV.errors import DAV_Error, DAV_NotFound
from DAV.errors import DAV_NotFound
from logging import debug
import sys
import urlparse
import os, string
import time
from string import joinfields, split, lower
import logging
import types
import shutil
import time
import base64

from DAV.constants import COLLECTION, OBJECT
from DAV.errors import *
from DAV.iface import *

from DAV.davcmd import copyone, copytree, moveone, movetree, delone, deltree

from sqlalchemy import create_engine
from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, DateTime, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import mapper, sessionmaker, relationship

import DAVServer
from base64 import b64decode
from Entity import ActionRestrict, User, TreeObject, Content, Group, Base,\
    ObjectRevision, ObjectProperty
from datetime import datetime
from actions import *
import hashlib


log = logging.getLogger(__name__)

BUFFER_SIZE = 128 * 1000 
# include magic support to correctly determine mimetypes
MAGIC_AVAILABLE = False
try:
    import mimetypes
    MAGIC_AVAILABLE = True
except ImportError:
    pass

class Resource(object):
    # XXX this class is ugly
    def __init__(self, fp, file_size):
        self.__fp = fp
        self.__file_size = file_size

    def __len__(self):
        return self.__file_size

    def __iter__(self):
        while 1:
            data = self.__fp.read(BUFFER_SIZE)
            if not data:
                break
            yield data
            time.sleep(0.005)
        self.__fp.close()

    def read(self, length = 0):
        if length == 0:
            length = self.__file_size

        data = self.__fp.read(length)
        return data
        

class DBFSHandler(dav_interface):
    """ 
    Model a filesystem for DAV

    This class models a regular filesystem for the DAV server

    The basic URL will be http://localhost/
    And the underlying filesystem will be /tmp
    
    """
    Base = declarative_base()
    
    
    
    def __init__(self, connection_string, uri, directory, verbose=False):
        self.setEngine(connection_string)
        self.setBaseURI(uri)
        # should we be verbose?
        self.verbose = verbose
        self.setDirectory(directory)
        log.info('Initialized with %s' % (uri))

    def setup(self):
        """Documentation"""
        sess = self.Session()
        
        if self.engine.has_table('Users') == False :
            self.metadata.create_all(self.engine)
            
            #create default objects
                       
            #default user
            
            
            root=User('root', hashlib.sha256('root').hexdigest(), 'root')            
            sess.add(root)
            toor=User('toor', hashlib.sha256('toor').hexdigest(), 'toor')            
            sess.add(toor)
            sess.commit()
            
            #default tree_object
            root_element=TreeObject("/",TreeObject.TYPE_COLLECTION,None,root.id,0,0,0,'/')
            sess.add(root_element)
            sess.commit()
            
            sess.add(ActionRestrict(root.id, 1, root_element.id, actions['ALL']))            
            sess.add(ActionRestrict(toor.id, 1, root_element.id, actions['ALL']))
            #
                        
            sess.commit()
            
            #add root group and subgroup. for test
            grp_base_dir= TreeObject("root_grp",TreeObject.TYPE_COLLECTION,root_element,0,0,0,0,'/root_grp/')
            
            sess.add(grp_base_dir)
            
            sess.commit()
            
            sess.add(ActionRestrict(root.id, 1, grp_base_dir.id, actions['ALL']))
            sess.add(ActionRestrict(toor.id, 1, grp_base_dir.id, actions['ALL']))
            
            grp = Group("root_grp",grp_base_dir)
            
            grp.users.append(root)
            grp.users.append(toor)
            
            sess.add(grp)
            sess.commit()
            
            sess.add(ActionRestrict(root.id, 1, grp.id, actions['ALL'], 2))
            sess.commit()
            
            sess.close()
    
    def setDirectory(self, path):
        """ Sets the directory """

        if not os.path.isdir(path):
            raise Exception, '%s not must be a directory!' % path

        self.directory = path
    
    def setEngine(self, connection_string):
        """ Set sqlalchemy engine"""
        
        self.metadata = Base.metadata
        self.engine = create_engine(connection_string, echo=True)
                
        self.Session = sessionmaker(bind=self.engine)
        
    def setCurrentUser(self, user):
        """set user for current session"""
        self.User = user    

    def setBaseURI(self, uri):
        """ Sets the base uri """

        self.baseuri = uri
    def uri2obj(self,uri, session = None):
        """ map uri in baseuri and local part """
        if session != None:
            sess = session
        else:
            sess = self.Session()

        uparts=urlparse.urlparse(uri)
        fileloc=uparts[2]        
        #get object id
        element=None
        #if fileloc.find(".history") != -1:
        #    parts = fileloc.split('/')
        #    
        #    if parts[-1] == "":
        #        element = TreeObject(parts[-2], TreeObject.TYPE_HISTORY, None, self.User, None, 0, None, fileloc)
        #    else:           
        #        element = TreeObject(parts[-1], TreeObject.TYPE_REV_FILE, None, self.User, None, 0, None, fileloc)
        #elif fileloc != '':        
        if fileloc != '':
            element = sess.query(TreeObject).filter_by(path=fileloc, is_deleted=False).first()
        else :
            element = sess.query(TreeObject).filter_by(id='1').first()
        
        if session == None:
            sess.close()

        if element == None:
            return None

        return element

    def object2uri(self,obj):
        """ map local filename to self.baseuri """
        uri=urlparse.urljoin(self.baseuri,obj.path)
        return uri


    def get_childs(self,uri):
        """        
        return the child objects as self.baseuris for the given URI
        
        handle root entity
        get all directories which append to
        user and user groups and add them as content of / directory
        adding files to / directory disallowed
        
        if uri isn't point to / get content of directory
        and if directory belongs to group, add available to user
        subgroup directories 
        """
        sess = self.Session()        
        obj=self.uri2obj(uri, sess)        
        filelist = []
        
        self.User = sess.merge(self.User)
        
        if obj.path == '/':
            for d in self.User.directories:
                if d.type == TreeObject.TYPE_COLLECTION:
                    filelist.append(self.object2uri(d))
            
            for g in self.User.groups:
                #for d in g.base_:
                if g.parent == None:
                    filelist.append(self.object2uri(g.base_dir))
        else:            
            if self._is_uri_group_directory(uri):
                for d in self._get_group_directories(uri):
                    filelist.append(self.object2uri(d))
                
            for elt in obj.nodes:                
                filelist.append(self.object2uri(elt))
        
        sess.close()
        
        return filelist

    def get_data(self,uri, range = None):
        """ return the content of an object """
        sess = self.Session()
        obj=self.uri2obj(uri, sess)
        print("getdata call\n")
        if obj.type == TreeObject.TYPE_FILE or obj.type == TreeObject.TYPE_REV_FILE:
            rev = obj.last_revision
            if rev == None :
                sess.close()
                raise DAV_Error
            
            path = "%s/%s" % (self.directory, rev.content.content)
        
        if os.path.exists(path):
            if os.path.isfile(path):
                file_size = os.path.getsize(path)
                if range == None:
                    fp=open(path,"r")
                    log.info('Serving content of %s' % uri)
                    return Resource(fp, file_size)
                else:
                    if range[1] == '':
                        range[1] = file_size
                    else:
                        range[1] = int(range[1])

                    if range[0] == '':
                        range[0] = file_size - range[1]
                    else:
                        range[0] = int(range[0])

                    if range[0] > file_size:
                        raise DAV_Requested_Range_Not_Satisfiable

                    if range[1] > file_size:
                        range[1] = file_size

                    fp=open(path,"r")
                    fp.seek(range[0])
                    log.info('Serving range %s -> %s content of %s' % (range[0], range[1], uri))
                    sess.close()
                    return Resource(fp, range[1] - range[0])
            else:
                # also raise an error for collections
                # don't know what should happen then..
                log.info('get_data: %s not found' % path)
        
        sess.close()
        
        raise DAV_Error

#            data = base64.b64decode(rev.content.content)
#            print("data recv: %s\n"%(data))
#            sess.close()
#            
#            if range == None:
#                return data 
#            else:
#                raise NotImplementedError

    def _get_dav_resourcetype(self,uri):
        """ return type of object """        
        obj=self.uri2obj(uri)
        if obj.type == TreeObject.TYPE_FILE:
            return OBJECT
        elif  obj.type == TreeObject.TYPE_COLLECTION:
            return COLLECTION

        raise DAV_NotFound

    def _get_dav_displayname(self,uri):

        obj = self.uri2obj(uri)
        return obj.name

    def _get_dav_getcontentlength(self,uri):
        """ return the content length of an object """
        sess=self.Session()
        obj=self.uri2obj(uri, sess)  
        if obj.type == TreeObject.TYPE_FILE:
            path = "%s/%s" % (self.directory, "%s_%i_%i" % (obj.name, obj.id, obj.last_revision.revision))
            sess.close()
            if os.path.exists(path):
                if os.path.isfile(path):
                    s=os.stat(path)
                    return str(s[6])

        return '0'

    def get_lastmodified(self,uri):
        """ return the last modified date of the object """
        # @type obj TreeObject
        obj = self.uri2obj(uri)

        return obj.mod_time
        

    def get_creationdate(self,uri):
        """ return the creation time of the object """
        # @type obj TreeObject
        obj = self.uri2obj(uri)

        return obj.creat_time

    def _get_dav_getcontenttype(self,uri):
        """ find out yourself! """
        sess=self.Session()
        
        obj=self.uri2obj(uri, sess)        
        rev = obj.last_revision
        
        if rev.content.mime_type == '':
            sess.close()
            return 'application/octet-stream'
        else:
            sess.close()
            return rev.content.mime_type

    def put(self, uri, data, content_type='application/octet-stream'):
        """ put the object into the filesystem """
        if self.User == None:
            raise DAV_Error( 401 )
        
        sess = self.Session()
        
        self.User = sess.merge(self.User)
        
        path = urlparse.urlparse(uri)[2]
        path_array = path.split('/')
        name = path_array[-1]
        parent_path = string.join(path_array[:-1],'/')+'/'
        if parent_path == '':            
            raise DAV_Forbidden
        
        parent = sess.query(TreeObject).filter_by(path=parent_path).first()

        if parent == None :
            raise DAV_Error

        obj = self.uri2obj(uri, sess)
        
        if obj == None:
            if self.User.groups == []:
                obj = TreeObject(name,TreeObject.TYPE_FILE,parent,self.User.id,None,0,0,path)
            else:                
                obj = TreeObject(name,TreeObject.TYPE_FILE,parent,self.User.id,self.User.groups[0].id,0,0,path)
        
            sess.add(obj)
            
            sess.commit()
            
            rest = sess.query(ActionRestrict).filter_by(actor_id=self.User.id, object_id=parent.id )
            
            for r in rest:
                sess.add(ActionRestrict(self.User.id, r.actor_type, obj.id, r.action ))
                
            sess.commit()
        
        obj.mod_time = time.time()
        
        try:
            prop = filter(lambda pr: pr, parent.properties)[0]            
        except IndexError:
            prop = None
        
        old_rev = obj.last_revision
        #obj.revisions
        if prop != None:
            rev = ObjectRevision()
            rev.mod_time = obj.mod_time
        
            if old_rev == None:
                rev.revision = 1            
            else:
                hist = self.uri2obj(string.join([parent.path[:-1],".history",""],'/'), sess)                           
                
                if hist != None:                    
                    prev_rev = ObjectRevision()
                    prev_rev.content = old_rev.content
                    prev_rev.revision = old_rev.revision
                    prev_rev.mod_time = old_rev.mod_time
                    rev.revision = old_rev.revision + 1
                    
                    prev_name = "%s_%s" % (name, datetime.fromtimestamp(old_rev.mod_time).strftime("%Y-%m-%d-%H-%M-%S"))    
                    prev = TreeObject(prev_name,TreeObject.TYPE_REV_FILE,hist,self.User.id,None,0,0,string.join([hist.path[:-1],prev_name],'/'))
#                    prev_file_path = "%s_%i_%i" % (name, obj.id, prev_rev.revision)
#                    prev_file_link = "%s_%i_%i" % (prev_name, obj.id, prev_rev.revision)
#                    
#                    os.symlink(prev_file_path, prev_file_link)
                    
                    sess.add(prev)
                    prev.revisions.append(prev_rev)                
                    
                    sess.commit() 
                    rest = sess.query(ActionRestrict).filter_by(actor_id=self.User.id, object_id=hist.id )       
                    sess.add(ActionRestrict(self.User.id, '1', prev.id, user_hist_acts ))
                    
                    sess.commit()
        else :
            if old_rev == None:
                rev = ObjectRevision()
                rev.mod_time = obj.mod_time
                rev.revision = 1
            else:
                rev = old_rev           
        if content_type == None:
            content_type = "application/octet-stream"
        
        if obj.id != None:
            file_path = "%s_%i_%i" % (name, obj.id, rev.revision)
        else:
            file_path = "%s_1_%i" % (name, rev.revision)
        
        try:
            fp=open("%s/%s" % (self.directory, file_path), "w+")
            if isinstance(data, types.GeneratorType):
                for d in data:
                    fp.write(d)
            else:
                if data:
                    fp.write(data)
            fp.close()
            log.info('put: Created %s' % uri)
        except:
            log.info('put: Could not create %s' % uri)
            raise DAV_Error, 424
        
        rev.content = Content(file_path, content_type) 
        
        obj.revisions.append(rev)                
        
        sess.add(obj)        
        sess.commit()
        sess.close()

    def mkhist(self, uri):
        if self.User == None:
            raise DAV_Error
        
        sess = self.Session()
        self.User = sess.merge(self.User)
        
        path = urlparse.urlparse(uri)[2][:-1]
        
        obj = self.uri2obj(uri, sess)
        
        rest = sess.query(ActionRestrict).filter_by(actor_id=self.User.id, object_id=obj.id )        
        hist = TreeObject(".history",TreeObject.TYPE_COLLECTION,obj,self.User.id,obj.group,0,0,string.join([path,".history",""],'/')) 
        
        sess.add(hist)
        sess.commit()
        
        for r in rest:
            sess.add(ActionRestrict(self.User.id, r.actor_type, hist.id, r.action | actions['HISTORY'] ))
        
        sess.commit()
        
        sess.close()

    def mkcol(self,uri):
        """ create a new collection """
        if self.User == None:
            raise DAV_Error
        
        path = urlparse.urlparse(uri)[2]
        print (path)
        sess = self.Session()
        self.User = sess.merge(self.User)
        
        path_array = path.split('/')
        name = path_array[-2]
        parent_path = string.join(path_array[:-2],'/')+'/'
        if parent_path == '':            
            parent_path='/'
        
        parent = sess.query(TreeObject).filter_by(path=parent_path).first()

        if parent == None :
            sess.close()
            raise DAV_Error
        
        rest = sess.query(ActionRestrict).filter_by(actor_id=self.User.id, object_id=parent.id )
        
        if self.User.groups == []:
            obj = TreeObject(name,TreeObject.TYPE_COLLECTION,parent,self.User.id,None,0,0,path)
        else:                
            obj = TreeObject(name,TreeObject.TYPE_COLLECTION,parent,self.User.id,self.User.groups[0].id,0,0,path)      
        
        sess.add(obj)
        
        if parent_path=='/':
            self.User.directories.append(obj)        

        sess.commit()
        
        if parent_path=='/':
            sess.add(ActionRestrict(self.User.id, '1', obj.id, actions['GET'] | actions['PROPFIND'] | actions['HEAD'] | actions['MKCOL'] | actions['USERINFO'] | actions['OPTIONS'] | actions['PUT'] | actions['LOCK'] | actions['UNLOCK'] | actions['COPY'] | actions['MOVE'] ))            
        else:
            for r in rest:
                sess.add(ActionRestrict(self.User.id, r.actor_type, obj.id, r.action ))
        #        
            
        sess.commit()        

    ### ?? should we do the handler stuff for DELETE, too ?
    ### (see below)

    def rmcol(self,uri):
        """ delete a collection """
        return self.rm(uri)

    def rm(self,uri):
        """ delete a normal resource """
        sess = self.Session()
        
        self.User = sess.merge(self.User)
        obj = self.uri2obj(uri)
        
        if obj == None:
            raise DAV_NotFound
        
        obj.is_deleted = True
        sess.add(obj)
        sess.commit()
        
        return 204

    ###
    ### DELETE handlers (examples)
    ### (we use the predefined methods in davcmd instead of doing
    ### a rm directly
    ###

    def delone(self,uri):
        """ delete a single resource

        You have to return a result dict of the form
        uri:error_code
        or None if everything's ok

        """
        return delone(self,uri)

    def deltree(self,uri):
        """ delete a collection 

        You have to return a result dict of the form
        uri:error_code
        or None if everything's ok
        """
        return deltree(self,uri)
        


    ###
    ### MOVE handlers (examples)
    ###

    def moveone(self,src,dst,overwrite):
        """ move one resource with Depth=0
        """

        return moveone(self,src,dst,overwrite)

    def movetree(self,src,dst,overwrite):
        """ move a collection with Depth=infinity
        """

        return movetree(self,src,dst,overwrite)

    ###
    ### COPY handlers
    ###

    def copyone(self,src,dst,overwrite):
        """ copy one resource with Depth=0
        """

        return copyone(self,src,dst,overwrite)

    def copytree(self,src,dst,overwrite):
        """ copy a collection with Depth=infinity
        """

        return copytree(self,src,dst,overwrite)

    ###
    ### copy methods.
    ### This methods actually copy something. low-level
    ### They are called by the davcmd utility functions
    ### copytree and copyone (not the above!)
    ### Look in davcmd.py for further details.
    ###

    def copy(self,src,dst):
        """ copy a resource from src to dst """
        if self.User == None:
            raise DAV_Error( 401 )
        
        sess=self.Session()
        source = self.uri2obj(src, sess)
        destination = self.uri2obj(dst, sess)
        
        if destination == None :
            path = urlparse.urlparse(destination)[2]
            path_array = path.split('/')
            name = path_array[-1]
            parent_path = string.join(path_array[:-1],'/')+'/'
            if parent_path == '':            
                raise DAV_Forbidden
            
            parent = sess.query(TreeObject).filter_by(path=parent_path).first()
    
            if parent == None :
                raise DAV_Error

            if self.User.groups == []:
                destination = TreeObject(name,TreeObject.TYPE_FILE,parent,self.User.id,None,0,0,path)
            else:                
                destination = TreeObject(name,TreeObject.TYPE_FILE,parent,self.User.id,self.User.groups[0].id,0,0,path)
        
            sess.add(destination)
            
            sess.commit()
            
            rest = sess.query(ActionRestrict).filter_by(actor_id=self.User.id, object_id=parent.id )
            
            for r in rest:
                sess.add(ActionRestrict(self.User.id, r.actor_type, destination.id, r.action ))
            
            rev = ObjectRevision()
            rev.mod_time = source.mod_time
            rev.revision = 1
            rev.content = source.content
            
            destination.revisions.append(rev)
                            
            sess.commit()
        else:
            old_rev = destination.last_revision   
                     
            try:
                prop = filter(lambda pr: pr, destination.properties)[0]            
            except IndexError:
                prop = None
                
            if prop != None:
                rev = ObjectRevision()
                rev.mod_time = source.mod_time
            
                if old_rev == None:
                    rev.revision = 1            
                else:
                    hist = self.uri2obj(string.join([destination.path[:-1],".history",""],'/'), sess)                           
                    
                    if hist != None:                    
                        prev_rev = ObjectRevision()
                        prev_rev.content = old_rev.content
                        prev_rev.revision = old_rev.revision
                        prev_rev.mod_time = old_rev.mod_time
                        rev.revision = old_rev.revision + 1
                        
                        prev_name = "%s_%s" % (destination.name, datetime.fromtimestamp(old_rev.mod_time).strftime("%Y-%m-%d-%H-%M-%S"))    
                        prev = TreeObject(prev_name,TreeObject.TYPE_REV_FILE,hist,self.User.id,None,0,0,string.join([hist.path[:-1],prev_name],'/'))
                       
                        sess.add(prev)
                        prev.revisions.append(prev_rev)                
                        
                        sess.commit() 
                        rest = sess.query(ActionRestrict).filter_by(actor_id=self.User.id, object_id=hist.id )       
                        sess.add(ActionRestrict(self.User.id, '1', prev.id, user_hist_acts ))
                        
                        sess.commit()
            else :
                if old_rev == None:
                    rev = ObjectRevision()
                    rev.mod_time = source.mod_time
                    rev.revision = 1
                else:
                    rev = old_rev
            
            rev.content = source.content
        
            destination.revisions.append(rev)                
            
            sess.add(destination)        
            sess.commit()    
            pass
        sess.close()
        

    def copycol(self, src, dst):
        """ copy a collection.

        As this is not recursive (the davserver recurses itself)
        we will only create a new directory here. For some more
        advanced systems we might also have to copy properties from
        the source to the destination.
        """

        return self.mkcol(dst)

    def exists(self,uri):
        """ test if a resource exists """
        return self.uri2obj(uri) != None

    def is_collection(self,uri):
        """ test if the given uri is a collection """

        return self._get_dav_resourcetype(uri) == COLLECTION
    
    def _is_uri_group_directory(self, uri):
        obj = self.uri2obj(uri)                
        sess = self.Session()        
        res = sess.query(Group).filter_by(base_dir=obj)
        sess.close()
        
        if res == None :
            return False
        
        return res.count() > 0
    
    def _get_group_directories(self, uri):
        filelist = []
        sess = self.Session()       
        obj = self.uri2obj(uri,sess)                
         
        res = sess.query(Group).filter_by(base_dir=obj).first()
        
        if res != None:
            for g in res.subgroups:
                #if g in self.User.groups:
                for gp in self.User.groups:
                    if g.id == gp.id:
                        filelist.append(g.base_dir)
        
        sess.close()
        
        
        return filelist
    
    def set_attr(self, uri, name, value):
        sess = self.Session()       
        obj = self.uri2obj(uri,sess)
        
        if obj == None:
            sess.close()
            return 404
        try:
            prop = filter(lambda prop: prop.name == name, obj.properties)[0]            
            prop.value = value
        except IndexError:
            obj.properties.append(ObjectProperty(name, value, obj));
        
        sess.add(obj)
        sess.commit()
        
        sess.close()
        mname="_set_dav_"+name
        try:
            m=getattr(self,mname)
            r=m(uri, value)
            return r
        except AttributeError:
            return 200 
        
        return 200
    
    def _set_dav_history(self, uri, value):
        sess = self.Session()       
        obj = self.uri2obj(uri,sess)
        
        if obj.type != TreeObject.TYPE_COLLECTION :            
            sess.close()
            return 409
        
        try:
            prop = filter(lambda r: r.name == ".history" !=0, obj.nodes)[0]
            if prop != None:
                sess.close()
                return 200            
        except IndexError:
            pass    
        
        rest = sess.query(ActionRestrict).filter_by(actor_id=self.User.id, object_id=obj.id )
        
        try:
            prop = filter(lambda r: r.action & actions['ADMIN'] !=0, rest)[0]            
        except IndexError:
            return 403
        
        self.mkhist(uri)
        return 200
    
    def _rm_dav_history(self,uri, name):
        sess = self.Session()       
        obj = self.uri2obj(uri,sess)
        
        if obj.type != TreeObject.TYPE_COLLECTION :            
            sess.close()
            return 409
        
        try:
            prop = filter(lambda r: r.name == "history" !=0, obj.properties)[0]
            if prop != None:
                sess.delete(prop)
                sess.commit()
                sess.close()
                return 200            
        except IndexError:
            return 404    
        
        return 200
    
    def _get_dav_history(self,uri):
        sess = self.Session()
        obj = self.uri2obj(uri,sess)
        
        try:
            prop = filter(lambda prop: prop.name == 'history', obj.properties)[0]
            sess.close()            
            
            return prop.value;
        except IndexError:
            sess.close()
            raise AttributeError;
        