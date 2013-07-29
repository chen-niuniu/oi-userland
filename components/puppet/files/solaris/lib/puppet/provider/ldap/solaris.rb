#
# CDDL HEADER START
#
# The contents of this file are subject to the terms of the
# Common Development and Distribution License (the "License").
# You may not use this file except in compliance with the License.
#
# You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
# or http://www.opensolaris.org/os/licensing.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# When distributing Covered Code, include this CDDL HEADER in each
# file and include the License file at usr/src/OPENSOLARIS.LICENSE.
# If applicable, add the following below this CDDL HEADER, with the
# fields enclosed by brackets "[]" replaced with your own identifying
# information: Portions Copyright [yyyy] [name of copyright owner]
#
# CDDL HEADER END
#

#
# Copyright (c) 2013, Oracle and/or its affiliates. All rights reserved.
#

Puppet::Type.type(:ldap).provide(:ldap) do
    desc "Provider for management of the LDAP client for Oracle Solaris"
    confine :operatingsystem => [:solaris]
    defaultfor :osfamily => :solaris, :kernelrelease => ['5.11', '5.12']
    commands :svccfg => '/usr/sbin/svccfg', :svcprop => '/usr/bin/svcprop'

    class << self; attr_accessor :ldap_fmri end
    @@ldap_fmri = "svc:/network/ldap/client"

    def self.instances
        if Process.euid != 0
            return []
        end
        props = {}
        validprops = Puppet::Type.type(:ldap).validproperties

        svcprop("-p", "config", @@ldap_fmri).split("\n").collect do |line|
            data = line.split()
            fullprop = data[0]
            type = data[1]
            if data.length > 2
                value = data[2..-1].join(" ")
            else
                value = nil
            end

            pg, prop = fullprop.split("/")

            # handle the domainname differently as it's not in validprops
            if prop == "profile"
                props[:name] = value
            else
                props[prop] = value if validprops.include? prop.to_sym
            end
        end
        props[:bind_passwd] = svcprop("-p", "cred/bind_passwd",
                                      "svc:/network/ldap/client").strip
        return Array new(props)
    end

    Puppet::Type.type(:ldap).validproperties.each do |field|
        # get the property group
        pg = Puppet::Type.type(:ldap).propertybyname(field).pg
        define_method(field) do
            begin
                svcprop("-p", pg + "/" + field.to_s, @@ldap_fmri).strip()
            rescue
                # if the property isn't set, don't raise an error
                nil
            end
        end

        define_method(field.to_s + "=") do |should|
            begin
                if should.is_a? Array
                    should.collect! { |value| value.to_s }

                    # the first entry needs the open paren and the last entry
                    # needs the close paren
                    should[0] = "(" + should[0]
                    should[-1] = should[-1] + ")"

                    svccfg("-s", @@ldap_fmri, "setprop",
                           pg + "/" + field.to_s, "=", should)
                else
                    svccfg("-s", @@ldap_fmri, "setprop",
                           pg + "/" + field.to_s, "=", should.to_s)
                end
                svccfg("-s", @@ldap_fmri, "refresh")
            rescue => detail
                raise Puppet::Error,
                    "Unable to set #{field.to_s} to #{should.inspect}\n"
                    "#{detail}\n"
            end
        end

    end
end
