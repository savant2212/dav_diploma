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

from DAV.errors import DAV_Error
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
from actions import actions
from sqlalchemy.sql.expression import desc
import DAVServer

log = logging.getLogger(__name__)

BUFFER_SIZE = 128 * 1000 
# include magic support to correctly determine mimetypes
MAGIC_AVAILABLE = False
try:
    import mimetypes
    MAGIC_AVAILABLE = True
except ImportError:
    pass

Base = declarative_base()



class ActionRestrict(Base):
    __tablename__='Restrictions'
    id          = Column(Integer, primary_key=True)
    actor_id    = Column(Integer)
    actor_type  = Column(Integer)    
    object_id   = Column(Integer)
    action   = Column(Integer)    

    def __init__(self, actor_id, actor_type, object_id, action):
        self.actor_id = actor_id
        self.actor_type = actor_type
        self.object_id = object_id
        self.action = action
        
     

# user data
user_group = Table(
    'UserGroups', Base.metadata,    
    Column('user_id', Integer, ForeignKey('Users.id')),
    Column('group_id', Integer, ForeignKey('Groups.id'))
    )

group_directory = Table(
    'GroupDirectories', Base.metadata,    
    Column('object_id', Integer, ForeignKey('TreeObjects.id')),
    Column('group_id', Integer, ForeignKey('Groups.id'))
    )

user_directory = Table(
    'UserDirectories', Base.metadata,    
    Column('object_id', Integer, ForeignKey('TreeObjects.id')),
    Column('user_id', Integer, ForeignKey('Users.id'))
    )
            
class User(Base):
    __tablename__='Users'
    id          = Column(Integer, primary_key=True)
    login       = Column(String)
    password    = Column(String)
    full_name   = Column(String)
    groups      = relationship("Group", secondary=user_group, backref='User')
    directories = relationship("TreeObject", secondary=user_directory, backref='User')
    is_deleted  = Column(Boolean,nullable=False)
    
    def __init__(self, login, password, full_name, is_deleted=False):
        self.login = login
        self.password = password
        self.full_name = full_name
        self.is_deleted = is_deleted
    

class Group(Base):
    __tablename__='Groups'
    id          = Column(Integer, primary_key=True)    
    name        = Column(String)
    users       = relationship("User", secondary=user_group, backref='Group')
    directories = relationship("TreeObject", secondary=group_directory, backref='Group')
    is_deleted  = Column(Boolean, nullable=False)
    def __init__(self, name, is_deleted=False):
        self.name=name
        self.is_deleted = is_deleted

#content
class Content(Base):
    __tablename__= 'Contents'

    id        = Column(Integer, primary_key=True)
    object_id = Column(Integer)
    revision  = Column(Integer)
    content   = Column(String)
    mod_time  = Column(Float)
    is_deleted  = Column(Boolean)

    def __init__(self, revision, content, tree_object, mod_time=time.time()):
        self.revision   = revision
        self.content    = content
        self.object_id  = tree_object
        mod_time        = mod_time

    def __repr__(self):
        return "<Content('%s','%s', '%s')>" % (self.tree_object, self.content, self.revision)


class TreeObject(Base):
    __tablename__= 'TreeObjects'
    id      = Column(Integer, primary_key=True)
    name    = Column(String)
    type    = Column(Integer)
    parent  = Column(Integer)
    owner   = Column(Integer)
    group   = Column(Integer)
    size    = Column(Integer)    
    path    = Column(String)
    mod_time = Column(Float)
    creat_time = Column(Float)
    is_deleted  = Column(Boolean, nullable=False)
    
    TYPE_COLLECTION = 1
    TYPE_FILE       = 0
    
    def __init__(self, name, type, parent, owner, group, size, content, path,
        creat_time=time.time(), mod_time=time.time(),is_deleted=False):
        self.name      = name
        self.type      = type
        self.parent    = parent
        self.owner     = owner
        self.group     = group
        self.size      = size
        self.content   = content
        self.path      = path
        self.mod_time  = mod_time
        self.creat_time= creat_time
        self.is_deleted= is_deleted

    def __repr__(self):
        return "<TreeObject('%s','%s','%s','%s','%s','%s','%s', '%s')>" % (
         self.name, self.type, self.parent, self.owner, self.group, self.size,
         self.content, self.path)

class DBFSHandler(dav_interface):
    """ 
    Model a filesystem for DAV

    This class models a regular filesystem for the DAV server

    The basic URL will be http://localhost/
    And the underlying filesystem will be /tmp
    
    """
    Base = declarative_base()
    
    
    
    def __init__(self, connection_string, uri, verbose=False):
        self.setEngine(connection_string)
        self.setBaseURI(uri)
        # should we be verbose?
        self.verbose = verbose
        log.info('Initialized with %s' % (uri))

    def setup(self):
        """Documentation"""
        sess = self.Session()
        
        if self.engine.has_table('Users') == False :
            self.metadata.create_all(self.engine)
            
            #create default objects
                       
            #default user
            root=User('root', 'root', 'root')            
            sess.add(root)
            sess.commit()
            
            #default tree_object
            root_element=TreeObject("/",TreeObject.TYPE_COLLECTION,None,root.id,0,0,0,'/')
            sess.add(root_element)
            sess.commit()
            
            sess.add(ActionRestrict(root.id, 1, root_element.id, actions['ALL']))            
            #
                        
            sess.commit()
            sess.close()

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
        
    def uri2obj(self,uri):
        """ map uri in baseuri and local part """
        sess = self.Session()

        uparts=urlparse.urlparse(uri)
        fileloc=uparts[2]        
        #get object id
        element=None
        if fileloc != '':
            element = sess.query(TreeObject).filter_by(path=fileloc, is_deleted=False).first()
        else :
            element = sess.query(TreeObject).filter_by(id='1').first()

        sess.close()

        if element == None:
            return None

        return element

    def object2uri(self,obj):
        """ map local filename to self.baseuri """
        uri=urlparse.urljoin(self.baseuri,obj.path)
        return uri


    def get_childs(self,uri):
        """ return the child objects as self.baseuris for the given URI """
        obj=self.uri2obj(uri)
        sess = self.Session()
        filelist = []
        
        self.User = sess.merge(self.User)
        # handle root entity
        # get all directories which append to
        # user and user groups and add them as content of / directory
        # disallow adding files to / directory
        # if uri isn't point to / just get content of directory
        if obj.path == '/':
            for d in self.User.directories:
                if d.type == TreeObject.TYPE_COLLECTION:
                    filelist.append(self.object2uri(d))
            
            for g in self.User.groups:
                for d in g.directories:
                    if d.type == TreeObject.TYPE_COLLECTION:
                        filelist.append(self.object2uri(d))
        else:
            for elt in sess.query(TreeObject).filter_by(parent=obj.id).order_by(TreeObject.name):
                print(elt.name)
                filelist.append(self.object2uri(elt))

        return filelist

    def get_data(self,uri, range = None):
        """ return the content of an object """
        obj=self.uri2obj(uri)
        if obj.type == TreeObject.TYPE_FILE:
            sess = self.Session()
            # @type content Content
            content = sess.query(Content).filter_by(object_id=obj.id).order_by(desc(Content.revision)).first()
            sess.close()

            if range == None:
                return base64.b64decode(content.content)
            else:
                raise NotImplementedError

        raise DAV_Error



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
        # @type obj TreeObject
        return obj.name

    def _get_dav_getcontentlength(self,uri):
        """ return the content length of an object """
        obj=self.uri2obj(uri)
        sess=self.Session()
        content = sess.query(Content).filter_by(object_id=obj.id).order_by(Content.revision).first()
        sess.close()
        data = base64.b64decode(content.content)
        return data.length

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
        return 'application/octet-stream'

    def put(self, uri, data, content_type=None):
        """ put the object into the filesystem """
        if self.User == None:
            raise DAV_Error( 401)
        
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

        obj = self.uri2obj(uri)
        
        if obj == None:
            if self.User.groups == []:
                obj = TreeObject(name,TreeObject.TYPE_FILE,parent.id,self.User.id,None,0,0,path)
            else:                
                obj = TreeObject(name,TreeObject.TYPE_FILE,parent.id,self.User.id,self.User.groups[0].id,0,0,path)
        
            sess.add(obj)
            
            sess.commit()
            
            rest = sess.query(ActionRestrict).filter_by(actor_id=self.User.id, object_id=parent.id )
            
            for r in rest:
                sess.add(ActionRestrict(self.User.id, r.actor_type, obj.id, r.action ))
                
            sess.commit()
        
        content = sess.query(Content).filter_by(object_id=obj.id).order_by(Content.revision).first()

        if content == None:
            content = Content(1,base64.b64encode(data), obj.id)
        else:
            
            content = Content(content.revision + 1,base64.b64encode(data), obj.id)

        sess.add(content)
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
            obj = DAVServer.myhandler.TreeObject(name,TreeObject.TYPE_COLLECTION,parent.id,self.User.id,None,0,0,path)
        else:                
            obj = DAVServer.myhandler.TreeObject(name,TreeObject.TYPE_COLLECTION,parent.id,self.User.id,self.User.groups[0].id,0,0,path)      
        
        sess.add(obj)        
        
        if parent_path=='/':
            self.User.directories.append(obj)

        sess.commit()
        
        for r in rest:
            sess.add(ActionRestrict(self.User.id, r.actor_type, obj.id, r.action ))
            
        sess.commit()        

    ### ?? should we do the handler stuff for DELETE, too ?
    ### (see below)

    def rmcol(self,uri):
        """ delete a collection """
        raise NotImplementedError

    def rm(self,uri):
        """ delete a normal resource """
        raise NotImplementedError

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
        raise NotImplementedError

    def deltree(self,uri):
        """ delete a collection 

        You have to return a result dict of the form
        uri:error_code
        or None if everything's ok
        """
        raise NotImplementedError
        


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
        sess=self.Session()
        source = self.uri2obj(src)
        

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

        return self._get_dav_resourcetype(self,uri) == COLLECTION
