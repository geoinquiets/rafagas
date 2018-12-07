require 'html-proofer'

options = { 
    :assume_extension => true ,
    :external_only => true,
    :typhoeus => { :ssl_verifyhost => 0 }

}
HTMLProofer.check_file(File.join(File.dirname(__FILE__), '../_site/index.html'), options).run