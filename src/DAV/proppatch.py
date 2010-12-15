#Copyright (c) 2010 Nikita Nazarenko (savant.d@gmail.com)
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

import xml.dom.minidom
from DAV.constants import HTTP_STATUS_LINES
domimpl = xml.dom.minidom.getDOMImplementation()

import logging
import sys
import string
import urlparse
import urllib
from StringIO import StringIO

import utils
from constants import COLLECTION, OBJECT, DAV_PROPS, RT_ALLPROP, RT_PROPNAME, RT_PROP
from errors import *

log = logging.getLogger(__name__)

class PROPPATCH:
    '''
    classdocs
    '''

    def __init__(self,uri,dataclass, body):
        '''
        Constructor
        '''
        self.nsmap={}
        self.set_props={}
        self.rm_props={}
        self.default_ns=None
        self._dataclass=dataclass
        
        self._uri=uri#.rstrip('/')
        self._has_body=None    # did we parse a body?

        if dataclass.verbose:
            log.info('PROPPATCH: URI is %s' % (uri))

        if body:
            self.set_props, self.rm_props = utils.parse_proppatch(body)
            self._has_body = True
            
    def createResponse(self):
        dc=self._dataclass
        # create the document generator
        doc = domimpl.createDocument(None, "multistatus", None)
        ms = doc.documentElement
        ms.setAttribute("xmlns:D", "DAV:")
        ms.tagName = 'D:multistatus'
        
        re=doc.createElement("D:response")
        
        uparts=urlparse.urlparse(self._uri)
        fileloc=uparts[2]
        href=doc.createElement("D:href")
        huri=doc.createTextNode(uparts[0]+'://'+'/'.join(uparts[1:2]) + urllib.quote(fileloc))
        href.appendChild(huri)
        re.appendChild(href)
 
        for name, value in self.set_props:
            ps=doc.createElement("D:propstat")
            # write prop element
            pr=doc.createElement("D:prop")
            attr = doc.createElement(name)
            status = doc.createElement('D:status')
            pr.appendChild(attr)
            
            ret = self._dataclass.set_attr(self._uri, name, value)
            
            status.appendChild(doc.createTextNode(HTTP_STATUS_LINES[ret]))
            
            ps.appendChild(pr)
            ps.appendChild(status)
            re.appendChild(ps)           
            
        for item in self.rm_props:
            ps=doc.createElement("D:propstat")
            pr=doc.createElement("D:prop")
            attr = doc.createElement(name)
            status = doc.createElement('D:status')
            pr.appendChild(attr)
            
            ret = self._dataclass.rm_attr(self._uri, name)
            
            status.appendChild(doc.createTextNode(HTTP_STATUS_LINES[ret]))  
            
            ps.appendChild(pr)
            ps.appendChild(status)
            re.appendChild(ps)        
        
        ms.appendChild(re)
        
        return doc.toxml(encoding="utf-8") 
    
    def set_response(self):
        pass
    
    def rm_response(self):
        pass       